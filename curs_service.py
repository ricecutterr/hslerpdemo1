"""
Serviciu curs valutar - preia cursul BNR și aplică multiplicator (default ×1.01)
pentru aproximarea cursului BT de vânzare.

BNR XML: https://www.bnr.ro/nbrfxrates.xml (actualizat zilnic ~13:00)
BNR Year: https://www.bnr.ro/files/xml/years/nbrfxrates{YYYY}.xml (istoric)
"""
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone, timedelta
import requests
import logging

log = logging.getLogger(__name__)

BNR_URL = 'https://www.bnr.ro/nbrfxrates.xml'
BNR_YEAR_URL = 'https://www.bnr.ro/files/xml/years/nbrfxrates{year}.xml'
DEFAULT_MULTIPLICATOR = 1.01  # BNR × 1.01 ≈ curs BT vânzare


def fetch_bnr_rate(moneda='EUR'):
    """Fetch current BNR rate for a currency from their XML feed."""
    try:
        resp = requests.get(BNR_URL, timeout=10)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)

        for cube in root.iter():
            if 'Cube' in cube.tag and cube.get('date'):
                bnr_date = cube.get('date')
                for rate in cube:
                    if rate.get('currency') == moneda:
                        multiplier = int(rate.get('multiplier', '1'))
                        value = float(rate.text) / multiplier
                        return value, bnr_date
        log.warning(f'Currency {moneda} not found in BNR XML')
        return None, None
    except Exception as e:
        log.error(f'Failed to fetch BNR rate: {e}')
        return None, None


def fetch_bnr_rate_for_date(target_date, moneda='EUR'):
    """Fetch BNR rate for a specific historical date from yearly XML.
    BNR doesn't publish on weekends/holidays, so we find the closest date <= target.
    
    Returns: (curs_bnr, actual_date_str) or (None, None)
    """
    url = BNR_YEAR_URL.format(year=target_date.year)
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)

        # Collect all dates with EUR rate
        rates = {}
        for cube in root.iter():
            if 'Cube' in cube.tag and cube.get('date'):
                cube_date = cube.get('date')
                for rate_el in cube:
                    if rate_el.get('currency') == moneda:
                        multiplier = int(rate_el.get('multiplier', '1'))
                        value = float(rate_el.text) / multiplier
                        rates[cube_date] = value

        if not rates:
            return None, None

        # Find exact date or closest before
        target_str = target_date.strftime('%Y-%m-%d')
        if target_str in rates:
            return rates[target_str], target_str

        # Find closest date <= target
        sorted_dates = sorted(rates.keys())
        best = None
        for d in sorted_dates:
            if d <= target_str:
                best = d
            else:
                break
        
        if best:
            return rates[best], best
        return None, None

    except Exception as e:
        log.error(f'Failed to fetch BNR yearly rate: {e}')
        return None, None


def get_curs_today(moneda='EUR', multiplicator=None):
    """Get today's exchange rate (BNR × multiplicator). Uses cache if available.
    
    Returns: (curs_final, curs_bnr) or (None, None) if unavailable
    """
    return get_curs_for_date(date.today(), moneda, multiplicator)


def get_curs_for_date(target_date, moneda='EUR', multiplicator=None):
    """Get exchange rate for a specific date (BNR × multiplicator). 
    Fetches from BNR if not cached.
    
    Returns: (curs_final, curs_bnr) or (None, None) if unavailable
    """
    from models import db, CursValutar

    if multiplicator is None:
        from models import Setari
        try:
            mult_str = Setari.get('curs_multiplicator', str(DEFAULT_MULTIPLICATOR))
            multiplicator = float(mult_str)
        except:
            multiplicator = DEFAULT_MULTIPLICATOR

    # Check cache
    cached = CursValutar.query.filter_by(data=target_date, moneda=moneda).first()
    if cached:
        return cached.curs_final, cached.curs_bnr

    # Fetch from BNR
    if target_date == date.today():
        curs_bnr, bnr_date = fetch_bnr_rate(moneda)
    else:
        curs_bnr, bnr_date = fetch_bnr_rate_for_date(target_date, moneda)

    if curs_bnr is None:
        # Fallback: closest cached rate
        closest = CursValutar.query.filter(
            CursValutar.moneda == moneda,
            CursValutar.data <= target_date
        ).order_by(CursValutar.data.desc()).first()
        if closest:
            return closest.curs_final, closest.curs_bnr
        return None, None

    curs_final = round(curs_bnr * multiplicator, 4)

    # Cache it
    try:
        cv = CursValutar(
            data=target_date, moneda=moneda,
            curs_bnr=curs_bnr, multiplicator=multiplicator,
            curs_final=curs_final, sursa='bnr',
        )
        db.session.add(cv)
        db.session.commit()
    except Exception:
        db.session.rollback()
        cached = CursValutar.query.filter_by(data=target_date, moneda=moneda).first()
        if cached:
            return cached.curs_final, cached.curs_bnr

    return curs_final, curs_bnr


def convert_eur_to_ron(amount_eur, curs=None):
    """Convert EUR amount to RON using today's rate.
    Returns: (amount_ron, curs_used)
    """
    if curs is None:
        curs, _ = get_curs_today('EUR')
    if curs is None:
        raise ValueError('Cursul valutar nu este disponibil. Verificați conexiunea la BNR.')
    return round(amount_eur * curs, 2), curs


def set_manual_rate(data, moneda, curs_manual):
    """Set a manual exchange rate for a specific date."""
    from models import db, CursValutar
    
    existing = CursValutar.query.filter_by(data=data, moneda=moneda).first()
    if existing:
        existing.curs_final = curs_manual
        existing.curs_bnr = curs_manual  # For manual, same
        existing.multiplicator = 1.0
        existing.sursa = 'manual'
        existing.data_preluare = datetime.now(timezone.utc)
    else:
        cv = CursValutar(
            data=data, moneda=moneda,
            curs_bnr=curs_manual, multiplicator=1.0,
            curs_final=curs_manual, sursa='manual',
        )
        db.session.add(cv)
    db.session.commit()
    return curs_manual
