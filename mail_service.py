"""
Gmail Integration Service for HSL ERP
- OAuth2 authentication flow
- Incremental inbox sync via Gmail API
- Send mail via Gmail API
- Auto-match sender to Client
"""
import os
import json
import base64
import email
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

# Scopes needed
SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/gmail.modify',
]

def get_credentials_path(app):
    """Path to Google OAuth client credentials JSON"""
    return os.path.join(app.root_path, 'gmail_credentials.json')


def get_oauth_flow(app, redirect_uri):
    """Create OAuth2 flow for Gmail"""
    creds_path = get_credentials_path(app)
    if not os.path.exists(creds_path):
        raise FileNotFoundError(
            'gmail_credentials.json lipsește. '
            'Descarcă-l din Google Cloud Console → APIs → Credentials → OAuth 2.0 Client ID → Download JSON'
        )
    flow = Flow.from_client_secrets_file(creds_path, scopes=SCOPES, redirect_uri=redirect_uri)
    return flow


def get_gmail_service(cont_mail):
    """Build Gmail API service from stored tokens"""
    creds = Credentials(
        token=cont_mail.access_token,
        refresh_token=cont_mail.refresh_token,
        token_uri='https://oauth2.googleapis.com/token',
        client_id=_get_client_id(cont_mail),
        client_secret=_get_client_secret(cont_mail),
        scopes=SCOPES
    )
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        # Update stored tokens
        cont_mail.access_token = creds.token
        cont_mail.token_expiry = creds.expiry
        from models import db
        db.session.commit()
    return build('gmail', 'v1', credentials=creds)


def _get_client_id(cont_mail):
    """Get client_id from credentials file"""
    creds_path = os.path.join(os.path.dirname(__file__), 'gmail_credentials.json')
    if os.path.exists(creds_path):
        with open(creds_path) as f:
            data = json.load(f)
            key = 'web' if 'web' in data else 'installed'
            return data[key]['client_id']
    return None


def _get_client_secret(cont_mail):
    """Get client_secret from credentials file"""
    creds_path = os.path.join(os.path.dirname(__file__), 'gmail_credentials.json')
    if os.path.exists(creds_path):
        with open(creds_path) as f:
            data = json.load(f)
            key = 'web' if 'web' in data else 'installed'
            return data[key]['client_secret']
    return None


# ═══════════════════════════════════════════════════════════
# SYNC
# ═══════════════════════════════════════════════════════════

def sync_inbox(cont_mail, max_results=50, max_pages=1):
    """Sync inbox messages from Gmail. Returns count of new messages."""
    from models import db, MailThread, MailMesaj, Client
    
    service = get_gmail_service(cont_mail)
    new_count = 0
    
    # Get recent messages (inbox + sent)
    query = 'in:inbox OR in:sent'
    if cont_mail.ultima_sincronizare:
        after = cont_mail.ultima_sincronizare - timedelta(minutes=5)
        after_ts = int(after.timestamp())
        query = f'({query}) after:{after_ts}'
    
    page_token = None
    for page in range(max_pages):
        try:
            params = dict(userId='me', q=query, maxResults=min(max_results, 100))
            if page_token:
                params['pageToken'] = page_token
            results = service.users().messages().list(**params).execute()
        except Exception as e:
            print(f'Gmail sync error for {cont_mail.email}: {e}')
            return -1
        
        messages = results.get('messages', [])
        
        for msg_ref in messages:
            gmail_msg_id = msg_ref['id']
            
            # Skip if already synced
            existing = MailMesaj.query.filter_by(gmail_msg_id=gmail_msg_id).first()
            if existing:
                continue
            
            # Fetch full message
            try:
                msg_data = service.users().messages().get(
                    userId='me', id=gmail_msg_id, format='full'
                ).execute()
            except Exception as e:
                print(f'Error fetching message {gmail_msg_id}: {e}')
                continue
            
            # Parse headers
            headers = {h['name'].lower(): h['value'] for h in msg_data.get('payload', {}).get('headers', [])}
            
            from_raw = headers.get('from', '')
            to_raw = headers.get('to', '')
            cc_raw = headers.get('cc', '')
            subject = headers.get('subject', '(fără subiect)')
            date_str = headers.get('date', '')
            
            # Parse email address from "Name <email>" format
            from_email = _extract_email(from_raw)
            from_name = _extract_name(from_raw)
            
            # Parse date
            msg_date = _parse_date(date_str, msg_data.get('internalDate'))
            
            # Determine direction
            is_sent = any(lbl in msg_data.get('labelIds', []) for lbl in ['SENT', 'DRAFT'])
            direction = 'trimis' if is_sent else 'primit'
            
            # Get/create thread
            gmail_thread_id = msg_data.get('threadId', gmail_msg_id)
            thread = MailThread.query.filter_by(
                gmail_thread_id=gmail_thread_id, cont_mail_id=cont_mail.id
            ).first()
            
            if not thread:
                thread = MailThread(
                    gmail_thread_id=gmail_thread_id,
                    cont_mail_id=cont_mail.id,
                    subiect=subject,
                    data_creare=msg_date or datetime.utcnow()
                )
                # Auto-match client by sender email
                if from_email and direction == 'primit':
                    client = Client.query.filter(
                        db.or_(
                            Client.email.ilike(f'%{from_email}%'),
                            Client.email_secundar.ilike(f'%{from_email}%') if hasattr(Client, 'email_secundar') else False
                        )
                    ).first()
                    if client:
                        thread.client_id = client.id
                db.session.add(thread)
                db.session.flush()
            
            # Parse body
            body_text, body_html = _parse_body(msg_data.get('payload', {}))
            
            # Parse attachments
            attachments = _parse_attachments(msg_data.get('payload', {}))
            
            # Create message
            mail_msg = MailMesaj(
                thread_id=thread.id,
                gmail_msg_id=gmail_msg_id,
                de_la=from_name or from_email,
                de_la_email=from_email,
                catre=to_raw,
                cc=cc_raw,
                subiect=subject,
                body_text=body_text,
                body_html=body_html,
                data_trimitere=msg_date,
                directie=direction,
                snippet=msg_data.get('snippet', '')[:300]
            )
            mail_msg.atasamente = attachments
            db.session.add(mail_msg)
            
            # Update thread metadata
            thread.ultimul_mesaj_data = msg_date
            thread.ultimul_mesaj_de_la = from_name or from_email
            thread.nr_mesaje = (thread.nr_mesaje or 0) + 1
            thread.are_atasamente = thread.are_atasamente or bool(attachments)
            if direction == 'primit':
                thread.citit = False  # Mark unread for new incoming
            
            new_count += 1
        
        # Next page?
        page_token = results.get('nextPageToken')
        if not page_token:
            break
    
    cont_mail.ultima_sincronizare = datetime.utcnow()
    db.session.commit()
    return new_count


# ═══════════════════════════════════════════════════════════
# SEND
# ═══════════════════════════════════════════════════════════

def send_mail(cont_mail, to, subject, body_html, cc=None, bcc=None, 
              reply_to_msg_id=None, attachments=None):
    """Send email via Gmail API. Returns gmail message id."""
    from models import db, MailThread, MailMesaj
    
    service = get_gmail_service(cont_mail)
    
    msg = MIMEMultipart('mixed')
    msg['From'] = cont_mail.email
    msg['To'] = to
    msg['Subject'] = subject
    if cc:
        msg['Cc'] = cc
    
    # Auto BCC
    bcc_list = []
    if bcc:
        bcc_list.append(bcc)
    if cont_mail.bcc_auto:
        bcc_list.extend([b.strip() for b in cont_mail.bcc_auto.split(',') if b.strip()])
    if bcc_list:
        msg['Bcc'] = ', '.join(bcc_list)
    
    # Reply headers
    gmail_thread_id = None
    if reply_to_msg_id:
        ref_msg = MailMesaj.query.filter_by(gmail_msg_id=reply_to_msg_id).first()
        if ref_msg:
            msg['In-Reply-To'] = f'<{reply_to_msg_id}>'
            msg['References'] = f'<{reply_to_msg_id}>'
            gmail_thread_id = ref_msg.thread.gmail_thread_id
    
    # Body
    msg.attach(MIMEText(body_html, 'html', 'utf-8'))
    
    # Attachments
    if attachments:
        for att in attachments:
            part = MIMEBase('application', 'octet-stream')
            part.set_payload(att['data'])
            encoders.encode_base64(part)
            part.add_header('Content-Disposition', f'attachment; filename="{att["name"]}"')
            msg.attach(part)
    
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    body = {'raw': raw}
    if gmail_thread_id:
        body['threadId'] = gmail_thread_id
    
    try:
        sent = service.users().messages().send(userId='me', body=body).execute()
        return sent.get('id')
    except Exception as e:
        print(f'Error sending mail from {cont_mail.email}: {e}')
        return None


def download_attachment(cont_mail, gmail_msg_id, att_id):
    """Download attachment data from Gmail"""
    service = get_gmail_service(cont_mail)
    try:
        att = service.users().messages().attachments().get(
            userId='me', messageId=gmail_msg_id, id=att_id
        ).execute()
        data = base64.urlsafe_b64decode(att['data'])
        return data
    except Exception as e:
        print(f'Error downloading attachment: {e}')
        return None


# ═══════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════

def _extract_email(raw):
    """Extract email from 'Name <email>' or just 'email'"""
    import re
    match = re.search(r'<([^>]+)>', raw)
    if match:
        return match.group(1).lower()
    if '@' in raw:
        return raw.strip().lower()
    return raw.strip().lower()


def _extract_name(raw):
    """Extract display name from 'Name <email>'"""
    import re
    match = re.match(r'^"?([^"<]+)"?\s*<', raw)
    if match:
        return match.group(1).strip()
    return None


def _parse_date(date_str, internal_date_ms=None):
    """Parse email date header or Gmail internalDate"""
    if internal_date_ms:
        try:
            return datetime.fromtimestamp(int(internal_date_ms) / 1000)
        except:
            pass
    if date_str:
        from email.utils import parsedate_to_datetime
        try:
            return parsedate_to_datetime(date_str).replace(tzinfo=None)
        except:
            pass
    return datetime.utcnow()


def _parse_body(payload):
    """Extract text and HTML body from Gmail message payload"""
    body_text = ''
    body_html = ''
    
    mime_type = payload.get('mimeType', '')
    
    if 'parts' in payload:
        for part in payload['parts']:
            t, h = _parse_body(part)
            if t and not body_text:
                body_text = t
            if h and not body_html:
                body_html = h
    else:
        data = payload.get('body', {}).get('data', '')
        if data:
            decoded = base64.urlsafe_b64decode(data).decode('utf-8', errors='replace')
            if 'text/plain' in mime_type:
                body_text = decoded
            elif 'text/html' in mime_type:
                body_html = decoded
    
    return body_text, body_html


def _parse_attachments(payload):
    """Extract attachment metadata from payload"""
    attachments = []
    
    if 'parts' in payload:
        for part in payload['parts']:
            filename = part.get('filename')
            if filename:
                att_id = part.get('body', {}).get('attachmentId')
                size = part.get('body', {}).get('size', 0)
                mime = part.get('mimeType', 'application/octet-stream')
                # Only include real attachments (with attachmentId), skip inline
                if att_id:
                    attachments.append({
                        'name': filename,
                        'size': size,
                        'mime': mime,
                        'gmail_att_id': att_id
                    })
            # Recurse into nested parts
            attachments.extend(_parse_attachments(part))
    
    return attachments
