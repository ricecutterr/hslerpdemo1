"""
Bank Reconciliation Service for HSL ERP
- CSV import (BT format)
- Auto-matching payments to invoices
- Mock data generator for testing
"""
import re
import csv
import io
from datetime import datetime, date, timedelta
from random import random, randint, choice


def parse_bt_csv(file_content, encoding='utf-8'):
    """Parse Banca Transilvania CSV export into transaction dicts.
    BT CSV format: Data, Descriere, Referinta, Debit, Credit, Sold
    Adapts to common BT export formats."""
    
    transactions = []
    
    try:
        if isinstance(file_content, bytes):
            file_content = file_content.decode(encoding, errors='replace')
    except:
        pass
    
    reader = csv.reader(io.StringIO(file_content), delimiter=',')
    header = None
    
    for row in reader:
        if not row or len(row) < 3:
            continue
        
        # Detect header row
        row_lower = [c.strip().lower() for c in row]
        if any(h in row_lower for h in ['data', 'date', 'data tranzactie']):
            header = row_lower
            continue
        
        if not header:
            # Try to detect by first column being a date
            try:
                _try_parse_date(row[0].strip())
                # Assume default BT format: Data, Descriere/Platitor, Referinta, Debit, Credit, Sold
                header = ['data', 'descriere', 'referinta', 'debit', 'credit', 'sold']
            except:
                continue
        
        try:
            data = {}
            for i, col in enumerate(header):
                if i < len(row):
                    data[col] = row[i].strip()
            
            # Parse date
            date_field = data.get('data') or data.get('date') or data.get('data tranzactie', '')
            trx_date = _try_parse_date(date_field)
            if not trx_date:
                continue
            
            # Parse amount (credit = incoming payment)
            credit = _parse_amount(data.get('credit', '') or data.get('suma credit', '') or '0')
            debit = _parse_amount(data.get('debit', '') or data.get('suma debit', '') or '0')
            
            if credit <= 0:
                continue  # Only interested in incoming payments
            
            # Extract payer info from description
            desc = data.get('descriere') or data.get('detalii') or data.get('explicatie') or ''
            ref = data.get('referinta') or data.get('referinta tranzactie') or ''
            
            payer_name, payer_iban, payer_cui = _extract_payer_info(desc)
            
            transactions.append({
                'data_tranzactie': trx_date,
                'suma': credit,
                'moneda': 'RON',
                'platitor_nume': payer_name or desc[:200],
                'platitor_iban': payer_iban or '',
                'platitor_cui': payer_cui or '',
                'referinta': ref[:200] if ref else '',
                'detalii': desc,
                'referinta_banca': f"BT-{trx_date.strftime('%Y%m%d')}-{credit:.2f}-{len(transactions)}"
            })
        except Exception as e:
            print(f'CSV parse error on row: {e}')
            continue
    
    return transactions


def _try_parse_date(s):
    """Try multiple date formats"""
    s = s.strip()
    for fmt in ['%d.%m.%Y', '%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y', '%m/%d/%Y']:
        try:
            return datetime.strptime(s, fmt).date()
        except:
            continue
    return None


def _parse_amount(s):
    """Parse amount string like '1.234,56' or '1234.56'"""
    s = s.strip().replace(' ', '')
    if not s or s == '0':
        return 0.0
    # Romanian format: 1.234,56
    if ',' in s and '.' in s:
        s = s.replace('.', '').replace(',', '.')
    elif ',' in s:
        s = s.replace(',', '.')
    try:
        return float(s)
    except:
        return 0.0


def _extract_payer_info(desc):
    """Extract payer name, IBAN, CUI from transaction description.
    BT CSV Descriere format (semicolon-separated):
      C.I.F.:17696129;prof.60170;KADRA TECH SRL;RO86BACX0000000490530000;BACXROBU;
      C.I.F.:34234332;factura proforma nr.61200, 11/02.20;26;642;GREEN MAGIC HOUSE CONSTRUCT SRL;RO83BTRL...;BTRLRO22;BTRLRO22;
      CV FFP 61236,61206;CONTAINERE FDC SRL;RO20RZBR0000060025955875;RZBRROBU;
    Structure: [CIF];[detalii...];COMPANY NAME;IBAN;BANK_CODE;[BANK_CODE;]
    The name is the segment right before the IBAN (which starts with RO + digits).
    """
    name = ''
    iban = ''
    cui = ''
    
    # CUI - BT uses C.I.F.:XXXXXXX
    cui_match = re.search(r'C\.I\.F\.:\s*(?:RO)?(\d{6,10})', desc, re.IGNORECASE)
    if not cui_match:
        cui_match = re.search(r'(?:CUI|CIF|cod fiscal)[:\s]*(?:RO)?(\d{6,10})', desc, re.IGNORECASE)
    if cui_match:
        cui = cui_match.group(1)
    
    # Split by semicolons and find IBAN → name is the segment before it
    parts = [p.strip() for p in desc.split(';') if p.strip()]
    
    iban_idx = -1
    for i, p in enumerate(parts):
        # IBAN: RO + 2 digits + 4 letters + rest (at least 16 chars total)
        if re.match(r'^RO\d{2}[A-Z]{4}', p.upper()):
            iban = p.upper()
            iban_idx = i
            break
    
    if iban_idx > 0:
        # Name is the segment right before IBAN
        candidate = parts[iban_idx - 1]
        # Verify it looks like a name (has letters, not just numbers/dates)
        if re.search(r'[A-Z]{2,}', candidate, re.IGNORECASE) and not candidate.startswith('C.I.F'):
            name = candidate
    
    if not name:
        # Fallback: look for known company suffixes
        for p in reversed(parts):
            if re.search(r'(?:SRL|S\.R\.L|SA|S\.A|PFA|SCS|II|ASOCIATI)', p, re.IGNORECASE):
                if not p.startswith('C.I.F'):
                    name = p
                    break
    
    if not name:
        # Last fallback: skip CIF part, take first meaningful text
        for p in parts:
            if not p.startswith('C.I.F') and re.search(r'[A-Z]{3,}', p, re.IGNORECASE):
                name = p
                break
    
    if not name:
        name = desc[:100]
    
    # Clean up
    name = re.sub(r'\s+', ' ', name).strip()
    
    return name, iban, cui


# ═══════════════════════════════════════════════════════════
# AUTO-MATCHING
# ═══════════════════════════════════════════════════════════

def auto_match(incasare, tolerance=0.01):
    """Try to automatically match a payment to an invoice.
    Returns (factura, match_type) or (None, None)."""
    from models import db, Factura, Client
    
    suma = incasare.suma
    detalii = (incasare.detalii or '') + ' ' + (incasare.referinta or '')
    platitor = incasare.platitor_nume or ''
    
    # ── Priority 1: Invoice reference in payment details ──
    # Look for patterns like PF-000123, PF/123, HSL-000123, HSL/123, factura 123, proforma 123
    ref_patterns = [
        r'(PF[\-/]\d+)',
        r'(?:proforma|pf)[:\s#]*(\d+)',
        r'(HSL[\-/]\d+)',
        r'(?:factura|fact|fct|inv)[:\s#]*(\d+)',
        r'(?:serie\s*(?:HSL|PF)\s*nr?\s*)(\d+)',
    ]
    for pat in ref_patterns:
        match = re.search(pat, detalii, re.IGNORECASE)
        if match:
            ref = match.group(1)
            # Extract number
            num_match = re.search(r'(\d+)', ref)
            if num_match:
                num = int(num_match.group(1))
                # Try proforma first, then fiscal
                factura = Factura.query.filter(
                    Factura.numar == num,
                    Factura.status.in_(['emisa', 'trimisa', 'partial']),
                    Factura.tip == 'proforma'
                ).first()
                if not factura:
                    factura = Factura.query.filter(
                        Factura.numar == num,
                        Factura.status.in_(['emisa', 'trimisa', 'partial'])
                    ).first()
                if factura and abs(factura.total - suma) < tolerance:
                    return factura, 'referinta'
    
    # ── Priority 2: Exact amount + client name match (prefer proforme) ──
    unpaid_pf = Factura.query.filter(
        Factura.status.in_(['emisa', 'trimisa', 'partial']),
        Factura.tip == 'proforma'
    ).all()
    unpaid_fc = Factura.query.filter(
        Factura.status.in_(['emisa', 'trimisa', 'partial']),
        Factura.tip == 'fiscala'
    ).all()
    unpaid = unpaid_pf + unpaid_fc  # Proforme first
    
    # Find by amount + name
    platitor_lower = platitor.lower()
    for f in unpaid:
        if abs(f.total - suma) < tolerance and f.client:
            client_name = f.client.nume.lower()
            # Check if payer name contains client name or vice versa
            if (client_name in platitor_lower or 
                platitor_lower in client_name or
                _fuzzy_name_match(platitor_lower, client_name)):
                return f, 'suma_client'
    
    # ── Priority 3: Exact amount, single match ──
    exact_matches = [f for f in unpaid if abs(f.total - suma) < tolerance]
    if len(exact_matches) == 1:
        return exact_matches[0], 'suma_unica'
    
    # ── Priority 4: CUI match + amount ──
    if incasare.platitor_cui:
        for f in unpaid:
            if f.client and f.client.cui and abs(f.total - suma) < tolerance:
                if f.client.cui.replace('RO', '') == incasare.platitor_cui.replace('RO', ''):
                    return f, 'cui_suma'
    
    return None, None


def _fuzzy_name_match(a, b):
    """Simple fuzzy matching for company names"""
    # Remove common suffixes
    clean = lambda s: re.sub(r'\b(srl|s\.r\.l|sa|s\.a|scs|pfa|ii|impex)\b', '', s).strip()
    a_clean = clean(a)
    b_clean = clean(b)
    if not a_clean or not b_clean:
        return False
    # Check if significant words overlap
    words_a = set(w for w in a_clean.split() if len(w) > 2)
    words_b = set(w for w in b_clean.split() if len(w) > 2)
    if not words_a or not words_b:
        return False
    overlap = words_a & words_b
    return len(overlap) >= min(len(words_a), len(words_b)) * 0.5


def _sync_related_invoices(factura):
    """When a fiscal invoice is paid, mark its related proforma as incasata too.
    When a proforma is paid, mark related fiscal as incasata too."""
    from models import Factura, Comanda
    
    if factura.tip == 'fiscala' and factura.comanda_id:
        # Fiscal paid → find proforma via comanda → oferta
        comanda = Comanda.query.get(factura.comanda_id)
        if comanda and comanda.oferta_id:
            proforme = Factura.query.filter_by(
                oferta_id=comanda.oferta_id, tip='proforma'
            ).filter(Factura.status.in_(['emisa', 'trimisa', 'confirmata'])).all()
            for pf in proforme:
                pf.status = 'incasata'
    
    elif factura.tip == 'proforma' and factura.oferta_id:
        # Proforma paid → find fiscal via oferta → comanda
        from models import Comanda as Cmd
        comanda = Cmd.query.filter_by(oferta_id=factura.oferta_id).first()
        if comanda:
            fiscale = Factura.query.filter_by(
                comanda_id=comanda.id, tip='fiscala'
            ).filter(Factura.status.in_(['emisa', 'trimisa'])).all()
            for fc in fiscale:
                fc.status = 'incasata'


def reconcile_batch(incasari_ids=None):
    """Run auto-matching on all unreconciled payments. Returns stats."""
    from models import db, Incasare, Factura
    
    q = Incasare.query.filter_by(status='nereconciliat')
    if incasari_ids:
        q = q.filter(Incasare.id.in_(incasari_ids))
    
    stats = {'total': 0, 'matched': 0, 'types': {}}
    
    for inc in q.all():
        stats['total'] += 1
        factura, match_type = auto_match(inc)
        if factura:
            inc.factura_id = factura.id
            inc.client_id = factura.client_id
            inc.status = 'automat'
            inc.data_reconciliere = datetime.now(timezone.utc)
            # Update invoice status
            total_incasat = sum(i.suma for i in factura.incasari if i.status in ('automat', 'manual'))
            total_incasat += inc.suma
            if total_incasat >= factura.total - 0.01:
                factura.status = 'incasata'
                # Cross-update: if fiscal is paid, mark related proforma as incasata too
                _sync_related_invoices(factura)
            else:
                factura.status = 'partial'
            stats['matched'] += 1
            stats['types'][match_type] = stats['types'].get(match_type, 0) + 1
    
    db.session.commit()
    return stats


# ═══════════════════════════════════════════════════════════
# MOCK DATA
# ═══════════════════════════════════════════════════════════

def generate_mock_transactions(count=15):
    """Generate realistic mock bank transactions for testing"""
    from models import db, Factura, Client
    
    companies = [
        'ACME CONSTRUCT SRL', 'DELTA BUILDING SA', 'EUROTERM INSTAL SRL',
        'MEGA DOORS IMPEX', 'NORD STEEL CONSTRUCT', 'PROIECT DESIGN SRL',
        'SIGMA INDUSTRIES SA', 'VEST CONSTRUCT SRL', 'ALPHA DOORS SRL',
        'BETA METAL CONSTRUCT', 'GAMMA INSTAL SRL', 'OMEGA BUILD SA'
    ]
    
    transactions = []
    
    # Get real unpaid invoices to create matching payments
    unpaid = Factura.query.filter(Factura.status.in_(['emisa', 'trimisa'])).all()
    
    for i in range(count):
        trx_date = date.today() - timedelta(days=randint(0, 30))
        
        if unpaid and i < len(unpaid) and random() < 0.6:
            # Create a payment that matches a real invoice
            f = unpaid[i]
            client_name = f.client.nume.upper() if f.client else choice(companies)
            suma = f.total
            ref = f'Plata factura {f.serie}/{f.numar}' if random() < 0.5 else f'Transfer {client_name}'
            detail = f'Incasare de la {client_name} - {ref}'
            if f.client and f.client.cui and random() < 0.3:
                detail += f' CUI {f.client.cui}'
        else:
            # Random transaction
            client_name = choice(companies)
            suma = round(randint(500, 50000) + random(), 2)
            ref = f'Transfer {client_name}'
            detail = f'Incasare de la {client_name} cont RO49BTRL{randint(1000,9999)}0{randint(10000000,99999999)}'
        
        transactions.append({
            'data_tranzactie': trx_date,
            'suma': suma,
            'moneda': 'RON',
            'platitor_nume': client_name,
            'platitor_iban': f'RO49BTRL{randint(1000,9999)}0{randint(10000000,99999999):08d}',
            'platitor_cui': '',
            'referinta': ref,
            'detalii': detail,
            'referinta_banca': f'MOCK-{trx_date.strftime("%Y%m%d")}-{i:04d}'
        })
    
    return transactions
