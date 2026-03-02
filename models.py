"""
HSL Solutions ERP - Unified Models
===================================
Flow: Client → Ofertă (Configurator) → Comandă → Factură → WMS

All models are interconnected:
- Client has Oferte, Comenzi, Facturi
- Oferta converts to Comanda (one-click)
- Comanda generates Factura
- WMS tracks stock movements linked to Comenzi
- Configurator products feed into Oferte lines
"""
import json
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime, date, timedelta, timezone
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

# ═══════════════════════════════════════════════════════════════
# AUTH & ROLES
# ═══════════════════════════════════════════════════════════════

# All available modules/permissions
MODULES = [
    # (key, label, icon, group)
    # ── GENERAL ──
    ('dashboard', 'Dashboard', 'bi-speedometer2', 'GENERAL'),
    ('chat', 'Chat', 'bi-chat-dots', 'GENERAL'),
    ('mail', 'Mail', 'bi-envelope', 'GENERAL'),
    # ── CRM ──
    ('crm', 'Clienți', 'bi-people', 'CRM'),
    # ── CATALOG ──
    ('nomenclator', 'Nomenclator Produse', 'bi-box', 'CATALOG'),
    # ── VÂNZĂRI ──
    ('oferte', 'Oferte (vizualizare, editare, ștergere, export)', 'bi-file-earmark-text', 'VÂNZĂRI'),
    ('oferte_comanda', 'Oferte → Transformare în Comandă', 'bi-cart-plus', 'VÂNZĂRI'),
    ('oferte_proforma', 'Oferte → Generare Proformă', 'bi-receipt-cutoff', 'VÂNZĂRI'),
    ('configurator', 'Configurator Oferte', 'bi-gear', 'VÂNZĂRI'),
    ('comenzi', 'Comenzi', 'bi-cart-check', 'VÂNZĂRI'),
    ('activitati', 'Activități (vizualizare)', 'bi-kanban', 'VÂNZĂRI'),
    ('activitati_status', 'Activități (schimbare status)', 'bi-toggle-on', 'VÂNZĂRI'),
    ('activitati_manage', 'Activități (gestiune completă)', 'bi-kanban-fill', 'VÂNZĂRI'),
    # ── FINANCIAR ──
    ('facturi', 'Facturi & Proforme', 'bi-receipt', 'FINANCIAR'),
    ('incasari', 'Încasări', 'bi-cash-coin', 'FINANCIAR'),
    ('raport_marja', 'Raport Marjă', 'bi-graph-up-arrow', 'FINANCIAR'),
    ('preturi_furnizor', 'Prețuri furnizor / achiziție / marjă', 'bi-currency-euro', 'FINANCIAR'),
    # ── LOGISTICĂ ──
    ('wms', 'WMS Dashboard', 'bi-box-seam', 'LOGISTICĂ'),
    ('wms_niruri', 'NIR-uri', 'bi-clipboard-check', 'LOGISTICĂ'),
    ('wms_furnizori', 'Furnizori', 'bi-truck', 'LOGISTICĂ'),
    ('wms_celule', 'Celule Depozit', 'bi-grid-3x3', 'LOGISTICĂ'),
    ('wms_necatalogate', 'Necatalogate', 'bi-question-circle', 'LOGISTICĂ'),
    ('wms_picking', 'Picking-uri', 'bi-cart-check', 'LOGISTICĂ'),
    ('wms_note_livrare', 'Note Livrare', 'bi-truck', 'LOGISTICĂ'),
    ('wms_transfer', 'Transfer Celule', 'bi-arrow-left-right', 'LOGISTICĂ'),
    ('wms_alerte', 'Alerte Stoc', 'bi-exclamation-triangle', 'LOGISTICĂ'),
    # ── ADMIN ──
    ('cfg_admin', 'Admin Configurator', 'bi-sliders', 'ADMIN'),
    ('utilizatori', 'Utilizatori & Roluri', 'bi-person-gear', 'ADMIN'),
    ('audit_log', 'Audit Log', 'bi-clock-history', 'ADMIN'),
]

MODULE_GROUPS = ['GENERAL', 'CRM', 'CATALOG', 'VÂNZĂRI', 'FINANCIAR', 'LOGISTICĂ', 'ADMIN']

class Rol(db.Model):
    __tablename__ = 'roluri'
    id = db.Column(db.Integer, primary_key=True)
    nume = db.Column(db.String(80), unique=True, nullable=False)
    descriere = db.Column(db.String(200))
    permisiuni = db.Column(db.Text, default='{}')  # JSON: {"crm": true, "oferte": true, ...}
    doar_proprii = db.Column(db.Boolean, default=True)  # Sees only own documents
    is_system = db.Column(db.Boolean, default=False)  # Can't be deleted (admin role)
    data_creare = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    utilizatori = db.relationship('Utilizator', backref='rol_obj', lazy='dynamic')

    def get_permisiuni(self):
        try:
            return json.loads(self.permisiuni) if self.permisiuni else {}
        except:
            return {}

    def set_permisiuni(self, perm_dict):
        self.permisiuni = json.dumps(perm_dict)

    def has_access(self, modul):
        if self.is_system:  # Admin role has access to everything
            return True
        return self.get_permisiuni().get(modul, False)

    def __repr__(self):
        return self.nume


class Utilizator(UserMixin, db.Model):
    __tablename__ = 'utilizatori'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    nume_complet = db.Column(db.String(200), nullable=False)
    telefon = db.Column(db.String(20))
    rol_id = db.Column(db.Integer, db.ForeignKey('roluri.id'))
    comision_procent = db.Column(db.Float, default=0.75)  # % comision din vanzari
    _dashboard_config = db.Column('dashboard_config', db.Text, default=None)
    activ = db.Column(db.Boolean, default=True)
    data_creare = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    last_seen = db.Column(db.DateTime)
    current_page = db.Column(db.String(200))

    @property
    def dashboard_config(self):
        try: return json.loads(self._dashboard_config) if self._dashboard_config else None
        except: return None
    @dashboard_config.setter
    def dashboard_config(self, val):
        self._dashboard_config = json.dumps(val, ensure_ascii=False) if val else None

    def set_password(self, pw):
        self.password_hash = generate_password_hash(pw)
    def check_password(self, pw):
        return check_password_hash(self.password_hash, pw)

    @property
    def rol_nume(self):
        return self.rol_obj.nume if self.rol_obj else 'Fără rol'

    @property
    def is_admin(self):
        return self.rol_obj and self.rol_obj.is_system

    @property
    def doar_proprii(self):
        return self.rol_obj.doar_proprii if self.rol_obj else True

    def has_access(self, modul):
        if not self.rol_obj:
            return False
        return self.rol_obj.has_access(modul)

    def __repr__(self):
        return self.nume_complet or self.username

# ═══════════════════════════════════════════════════════════════
# CRM - CLIENTI
# ═══════════════════════════════════════════════════════════════

class Client(db.Model):
    __tablename__ = 'clienti'
    id = db.Column(db.Integer, primary_key=True)
    # Identity
    nume = db.Column(db.String(200), nullable=False)
    tip = db.Column(db.String(20), default='companie')  # companie, persoana_fizica
    cui = db.Column(db.String(20), unique=True, nullable=True)
    nr_reg_com = db.Column(db.String(50))
    # Contact
    email = db.Column(db.String(120))
    telefon = db.Column(db.String(20))
    telefon_secundar = db.Column(db.String(20))
    persoana_contact = db.Column(db.String(200))
    # Address
    adresa = db.Column(db.Text)
    oras = db.Column(db.String(100))
    judet = db.Column(db.String(100))
    cod_postal = db.Column(db.String(10))
    tara = db.Column(db.String(100), default='România')
    # Banking
    banca = db.Column(db.String(200))
    iban = db.Column(db.String(34))
    # Status
    activ = db.Column(db.Boolean, default=True)
    observatii = db.Column(db.Text)
    sablon_pret_id = db.Column(db.Integer, db.ForeignKey('cfg_sabloane_preturi.id'), nullable=True)
    data_creare = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    data_modificare = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # === RELATIONSHIPS (Client is the HUB) ===
    oferte = db.relationship('Oferta', backref='client', lazy='dynamic')
    comenzi = db.relationship('Comanda', backref='client', lazy='dynamic')
    facturi = db.relationship('Factura', backref='client', lazy='dynamic')
    sablon_pret = db.relationship('SablonListaPreturi', backref='clienti')

    @property
    def nr_oferte(self):
        return self.oferte.count()
    @property
    def nr_comenzi(self):
        return self.comenzi.count()
    @property
    def valoare_totala(self):
        return sum(c.total or 0 for c in self.comenzi.filter(Comanda.status != 'anulat'))

    def __repr__(self):
        return self.nume

# ═══════════════════════════════════════════════════════════════
# CONFIGURATOR - CATEGORII PRODUSE & ACCESORII
# ═══════════════════════════════════════════════════════════════

class CategorieProdus(db.Model):
    __tablename__ = 'cfg_categorii_produse'
    id = db.Column(db.Integer, primary_key=True)
    nume = db.Column(db.String(100), nullable=False)
    descriere = db.Column(db.Text)
    ordine = db.Column(db.Integer, default=0)

class CategorieAccesoriu(db.Model):
    __tablename__ = 'cfg_categorii_accesorii'
    id = db.Column(db.Integer, primary_key=True)
    nume = db.Column(db.String(100), nullable=False)
    descriere = db.Column(db.Text)
    ordine = db.Column(db.Integer, default=0)

# ═══════════════════════════════════════════════════════════════
# CONFIGURATOR - PRODUSE (cu parametri, variante, prețuri)
# ═══════════════════════════════════════════════════════════════

class ProdusConfig(db.Model):
    """Products available in the configurator (fire doors, windows, etc.)"""
    __tablename__ = 'cfg_produse'
    id = db.Column(db.Integer, primary_key=True)
    cod = db.Column(db.String(50), unique=True, nullable=False)
    denumire = db.Column(db.String(300), nullable=False)
    descriere = db.Column(db.Text)
    pret = db.Column(db.Float, default=0)  # = Preț listă HSL (prețul de catalog HSL)
    um = db.Column(db.String(20), default='buc')
    activ = db.Column(db.Boolean, default=True)
    # Pricing chain: furnizor → achiziție → minim vânzare → listă HSL
    pret_furnizor = db.Column(db.Float, default=0)     # Preț listă furnizor
    discount_furnizor = db.Column(db.Float, default=0)  # Discount furnizor %
    adaos_hsl = db.Column(db.Float, default=0)          # Adaos HSL %
    # JSON configs
    _parametri_config = db.Column('parametri_config', db.Text, default='[]')
    _variante_config = db.Column('variante_config', db.Text, default='{}')
    categorii = db.relationship('ProdusCategorie', backref='produs', cascade='all, delete-orphan')

    @property
    def pret_achizitie(self):
        """Preț furnizor × (1 - discount/100)"""
        return self.pret_furnizor * (1 - (self.discount_furnizor or 0) / 100)
    @property
    def pret_minim_vanzare(self):
        """Preț achiziție × (1 + adaos/100)"""
        return self.pret_achizitie * (1 + (self.adaos_hsl or 0) / 100)
    @property
    def pret_lista_hsl(self):
        """Alias for pret - prețul de catalog HSL"""
        return self.pret or 0
    @pret_lista_hsl.setter
    def pret_lista_hsl(self, val):
        self.pret = val

    @property
    def parametri_config(self):
        try: return json.loads(self._parametri_config or '[]')
        except: return []
    @parametri_config.setter
    def parametri_config(self, val):
        self._parametri_config = json.dumps(val, ensure_ascii=False)
    @property
    def variante_config(self):
        try: return json.loads(self._variante_config or '{}')
        except: return {}
    @variante_config.setter
    def variante_config(self, val):
        self._variante_config = json.dumps(val, ensure_ascii=False)
    def __repr__(self):
        return f'{self.cod} - {self.denumire}'

class ProdusCategorie(db.Model):
    __tablename__ = 'cfg_produs_categorii'
    id = db.Column(db.Integer, primary_key=True)
    produs_id = db.Column(db.Integer, db.ForeignKey('cfg_produse.id'), nullable=False)
    categorie_id = db.Column(db.Integer, db.ForeignKey('cfg_categorii_produse.id'), nullable=False)

# ═══════════════════════════════════════════════════════════════
# CONFIGURATOR - ACCESORII
# ═══════════════════════════════════════════════════════════════

class ProdusLegatura(db.Model):
    """Many-to-many link between products (e.g. door leaf ↔ frame)"""
    __tablename__ = 'cfg_produs_legaturi'
    id = db.Column(db.Integer, primary_key=True)
    produs_a_id = db.Column(db.Integer, db.ForeignKey('cfg_produse.id'), nullable=False)
    produs_b_id = db.Column(db.Integer, db.ForeignKey('cfg_produse.id'), nullable=False)
    # Display settings: which product is shown first (principal) and which provides dimension/price
    # Values: 'a' or 'b' — refers to produs_a or produs_b; 'both' for price_source
    principal = db.Column(db.String(1), default='a')  # who shows as main line
    dim_source = db.Column(db.String(1), default='a')  # who provides the dimension
    price_source = db.Column(db.String(4), default='both')  # 'a', 'b', or 'both'
    # JSON: mapping of variant compatibility
    _compatibilitati = db.Column('compatibilitati', db.Text, default='[]')

    produs_a = db.relationship('ProdusConfig', foreign_keys=[produs_a_id], backref='legaturi_a')
    produs_b = db.relationship('ProdusConfig', foreign_keys=[produs_b_id], backref='legaturi_b')

    @property
    def compatibilitati(self):
        try: return json.loads(self._compatibilitati or '[]')
        except: return []
    @compatibilitati.setter
    def compatibilitati(self, val):
        self._compatibilitati = json.dumps(val, ensure_ascii=False)

class Accesoriu(db.Model):
    __tablename__ = 'cfg_accesorii'
    id = db.Column(db.Integer, primary_key=True)
    cod = db.Column(db.String(50), unique=True, nullable=False)
    denumire = db.Column(db.String(300), nullable=False)
    descriere = db.Column(db.Text)
    tip = db.Column(db.String(20), default='accesoriu')
    pret = db.Column(db.Float, default=0)  # = Preț listă HSL
    pret_mode = db.Column(db.String(20), default='fix')  # fix, per_mp, per_ml
    um = db.Column(db.String(20), default='buc')
    poate_standalone = db.Column(db.Boolean, default=True)
    activ = db.Column(db.Boolean, default=True)
    categorie_id = db.Column(db.Integer, db.ForeignKey('cfg_categorii_accesorii.id'))
    # Pricing chain
    pret_furnizor = db.Column(db.Float, default=0)
    discount_furnizor = db.Column(db.Float, default=0)
    adaos_hsl = db.Column(db.Float, default=0)
    categorie = db.relationship('CategorieAccesoriu', backref='accesorii')
    compatibilitati = db.relationship('AccesoriuCompat', backref='accesoriu', cascade='all, delete-orphan')

    @property
    def pret_achizitie(self):
        return self.pret_furnizor * (1 - (self.discount_furnizor or 0) / 100)
    @property
    def pret_minim_vanzare(self):
        return self.pret_achizitie * (1 + (self.adaos_hsl or 0) / 100)
    @property
    def pret_lista_hsl(self):
        return self.pret or 0

    def __repr__(self):
        return f'{self.cod} - {self.denumire}'

class AccesoriuCompat(db.Model):
    __tablename__ = 'cfg_accesoriu_compat'
    id = db.Column(db.Integer, primary_key=True)
    accesoriu_id = db.Column(db.Integer, db.ForeignKey('cfg_accesorii.id'), nullable=False)
    produs_id = db.Column(db.Integer, db.ForeignKey('cfg_produse.id'), nullable=False)
    status = db.Column(db.String(20), default='optional')  # standard, optional
    # JSON: list of variant suffixes this accessory is compatible with
    # Empty/null = compatible with ALL variants (backward compatible)
    # e.g. [".19010", ".29010"] = only these variants
    _variante_compat = db.Column('variante_compat', db.Text, default='[]')

    @property
    def variante_compat(self):
        try: return json.loads(self._variante_compat or '[]')
        except: return []
    @variante_compat.setter
    def variante_compat(self, val):
        self._variante_compat = json.dumps(val, ensure_ascii=False)

# ═══════════════════════════════════════════════════════════════
# LISTE DE PREȚURI - ȘABLOANE
# ═══════════════════════════════════════════════════════════════

class SablonListaPreturi(db.Model):
    """Price list template - applied to clients for custom pricing"""
    __tablename__ = 'cfg_sabloane_preturi'
    id = db.Column(db.Integer, primary_key=True)
    nume = db.Column(db.String(200), nullable=False)
    descriere = db.Column(db.Text)
    discount_global = db.Column(db.Float, default=0)  # % discount global pe toate produsele
    activ = db.Column(db.Boolean, default=True)
    data_creare = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    # JSON: per-category and per-product discounts
    # Format: {"categorii": {cat_id: discount%}, "produse": {produs_id: discount%}}
    _reguli = db.Column('reguli', db.Text, default='{}')

    @property
    def reguli(self):
        try: return json.loads(self._reguli or '{}')
        except: return {}
    @reguli.setter
    def reguli(self, val):
        self._reguli = json.dumps(val, ensure_ascii=False)

    def get_discount(self, produs_id, categorie_ids=None, variant_suffix=None):
        """Get effective discount for a product/variant. Priority: variant > produs > categorie > global"""
        r = self.reguli
        # Per-variant override
        if variant_suffix:
            var_discounts = r.get('variante', {})
            var_key = str(produs_id) + '_' + variant_suffix
            if var_key in var_discounts and var_discounts[var_key] is not None:
                return float(var_discounts[var_key])
        # Per-product override
        prod_discounts = r.get('produse', {})
        pid_str = str(produs_id)
        if pid_str in prod_discounts and prod_discounts[pid_str] is not None:
            return float(prod_discounts[pid_str])
        # Per-category override (highest discount wins)
        cat_discounts = r.get('categorii', {})
        if categorie_ids and cat_discounts:
            best = None
            for cid in categorie_ids:
                cid_str = str(cid)
                if cid_str in cat_discounts and cat_discounts[cid_str] is not None:
                    d = float(cat_discounts[cid_str])
                    if best is None or d > best:
                        best = d
            if best is not None:
                return best
        # Global default
        return self.discount_global or 0

    def __repr__(self):
        return self.nume

# ═══════════════════════════════════════════════════════════════
# VÂNZĂRI - OFERTE (created by Configurator)
# ═══════════════════════════════════════════════════════════════

class Oferta(db.Model):
    """Quote/Offer - created in Configurator, can be converted to Comanda"""
    __tablename__ = 'oferte'
    STATUSES = [('draft','Draft'),('trimisa','Trimisă'),('acceptata','Acceptată'),
                ('refuzata','Refuzată'),('expirata','Expirată'),('comanda','Convertită')]
    METODE_FOLLOWUP = [('telefon','Telefon'),('email','Email'),('intalnire','Întâlnire'),
                        ('whatsapp','WhatsApp'),('altele','Altele')]
    REZULTATE_FOLLOWUP = [('interesat','Interesat'),('revine','Revine cu răspuns'),
                           ('cere_modificari','Cere modificări'),('fara_raspuns','Fără răspuns'),
                           ('refuza','Refuză'),('accepta','Acceptă')]

    id = db.Column(db.Integer, primary_key=True)
    numar = db.Column(db.String(50), unique=True, nullable=False)
    versiune = db.Column(db.Integer, default=1)
    parinte_id = db.Column(db.Integer, db.ForeignKey('oferte.id'), nullable=True)
    client_id = db.Column(db.Integer, db.ForeignKey('clienti.id'))
    status = db.Column(db.String(20), default='draft')
    data_oferta = db.Column(db.Date, default=date.today)
    data_expirare = db.Column(db.Date)
    valabilitate_zile = db.Column(db.Integer, default=30)
    discount_mode = db.Column(db.String(20), default='individual')
    discount_global = db.Column(db.Float, default=0)
    subtotal = db.Column(db.Float, default=0)
    tva_procent = db.Column(db.Float, default=19)
    tva_valoare = db.Column(db.Float, default=0)
    total = db.Column(db.Float, default=0)
    moneda = db.Column(db.String(3), default='EUR')
    observatii = db.Column(db.Text)
    data_creare = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    creat_de_id = db.Column(db.Integer, db.ForeignKey('utilizatori.id'))
    creat_de = db.relationship('Utilizator', foreign_keys=[creat_de_id])

    # Relationship to lines, order, revisions, follow-ups
    linii = db.relationship('LinieOferta', backref='oferta', cascade='all, delete-orphan',
                            order_by='LinieOferta.ordine')
    comanda = db.relationship('Comanda', backref='oferta_sursa', uselist=False)
    revizii = db.relationship('Oferta', backref=db.backref('parinte', remote_side='Oferta.id'),
                               foreign_keys=[parinte_id], order_by='Oferta.versiune')
    followups = db.relationship('FollowUpOferta', backref='oferta', cascade='all, delete-orphan',
                                 order_by='FollowUpOferta.data_followup.desc()')
    proforme = db.relationship('Factura', foreign_keys='Factura.oferta_id',
                               lazy='dynamic')

    @property
    def numar_display(self):
        """Show OF-xxx v2 for revisions"""
        base = self.parinte.numar if self.parinte else self.numar
        return f'{base} v{self.versiune}' if self.versiune > 1 else self.numar

    @property
    def next_followup(self):
        """Next planned follow-up date"""
        fu = FollowUpOferta.query.filter(
            FollowUpOferta.oferta_id == self.id,
            FollowUpOferta.next_date != None,
            FollowUpOferta.next_date >= date.today()
        ).order_by(FollowUpOferta.next_date.asc()).first()
        return fu.next_date if fu else None

    @property
    def ultima_versiune(self):
        """Get the latest version in this offer chain"""
        if self.revizii:
            return max(self.revizii, key=lambda r: r.versiune)
        return self

    def recalculeaza(self):
        self.subtotal = sum(l.pret_final * l.cantitate for l in self.linii)
        self.tva_valoare = self.subtotal * self.tva_procent / 100
        self.total = self.subtotal + self.tva_valoare

    def __repr__(self):
        return f'Oferta {self.numar}'

class LinieOferta(db.Model):
    __tablename__ = 'linii_oferta'
    id = db.Column(db.Integer, primary_key=True)
    oferta_id = db.Column(db.Integer, db.ForeignKey('oferte.id'), nullable=False)
    ordine = db.Column(db.Integer, default=0)
    tip = db.Column(db.String(20), default='Produs')  # Produs, Accesoriu
    cod = db.Column(db.String(100))
    denumire = db.Column(db.String(500))
    dimensiune = db.Column(db.String(100))
    um = db.Column(db.String(20), default='buc')
    cantitate = db.Column(db.Float, default=1)
    pret_catalog = db.Column(db.Float, default=0)
    discount_adaos = db.Column(db.Float, default=0)
    pret_final = db.Column(db.Float, default=0)
    is_sub_line = db.Column(db.Boolean, default=False)
    parent_cod = db.Column(db.String(100))
    _parametri = db.Column('parametri_json', db.Text, default='{}')
    _accesorii = db.Column('accesorii_json', db.Text, default='[]')

    @property
    def parametri(self):
        try: return json.loads(self._parametri or '{}')
        except: return {}
    @parametri.setter
    def parametri(self, v):
        self._parametri = json.dumps(v, ensure_ascii=False)
    @property
    def accesorii(self):
        try: return json.loads(self._accesorii or '[]')
        except: return []
    @accesorii.setter
    def accesorii(self, v):
        self._accesorii = json.dumps(v, ensure_ascii=False)
    @property
    def valoare_linie(self):
        return round(self.pret_final * self.cantitate, 2)


class FollowUpOferta(db.Model):
    """Follow-up tracking on offers"""
    __tablename__ = 'followups_oferte'
    id = db.Column(db.Integer, primary_key=True)
    oferta_id = db.Column(db.Integer, db.ForeignKey('oferte.id'), nullable=False)
    data_followup = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    metoda = db.Column(db.String(20), default='telefon')  # telefon, email, intalnire, whatsapp
    rezultat = db.Column(db.String(20), default='interesat')
    note = db.Column(db.Text)
    next_date = db.Column(db.Date, nullable=True)  # when to follow up next
    creat_de_id = db.Column(db.Integer, db.ForeignKey('utilizatori.id'))
    creat_de = db.relationship('Utilizator', foreign_keys=[creat_de_id])

    @property
    def metoda_icon(self):
        icons = {'telefon':'bi-telephone','email':'bi-envelope','intalnire':'bi-people',
                 'whatsapp':'bi-whatsapp','altele':'bi-chat-dots'}
        return icons.get(self.metoda, 'bi-chat-dots')


# ═══════════════════════════════════════════════════════════════
# VÂNZĂRI - COMENZI (from accepted Oferte OR manual)
# ═══════════════════════════════════════════════════════════════

class Comanda(db.Model):
    """Order - created from accepted Oferta or manually"""
    __tablename__ = 'comenzi'
    STATUSES = [('pending','Așteptare Aprobare'),('noua','Nouă'),('confirmata','Confirmată'),('productie','În Producție'),
                ('gata','Gata de Livrare'),('livrata','Livrată'),('finalizata','Finalizată'),
                ('anulat','Anulată')]
    id = db.Column(db.Integer, primary_key=True)
    numar = db.Column(db.String(50), unique=True, nullable=False)
    client_id = db.Column(db.Integer, db.ForeignKey('clienti.id'), nullable=True)
    oferta_id = db.Column(db.Integer, db.ForeignKey('oferte.id'), nullable=True)  # Link back
    status = db.Column(db.String(20), default='noua')
    data_comanda = db.Column(db.Date, default=date.today)
    data_livrare_estimata = db.Column(db.Date)
    data_livrare_efectiva = db.Column(db.Date)
    # Financial (copied from Oferta at conversion)
    subtotal = db.Column(db.Float, default=0)
    discount_procent = db.Column(db.Float, default=0)
    tva_procent = db.Column(db.Float, default=19)
    tva_valoare = db.Column(db.Float, default=0)
    total = db.Column(db.Float, default=0)
    moneda = db.Column(db.String(3), default='EUR')
    adresa_livrare = db.Column(db.Text)
    observatii = db.Column(db.Text)
    data_creare = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    creat_de_id = db.Column(db.Integer, db.ForeignKey('utilizatori.id'))
    creat_de = db.relationship('Utilizator', foreign_keys=[creat_de_id])

    linii = db.relationship('LinieComanda', backref='comanda', cascade='all, delete-orphan',
                            order_by='LinieComanda.ordine')
    facturi = db.relationship('Factura', backref='comanda', lazy='dynamic')
    miscari_stoc = db.relationship('MiscareStoc', backref='comanda', lazy='dynamic')
    activitati = db.relationship('Activitate', backref='comanda', lazy='dynamic',
                                  foreign_keys='Activitate.comanda_id')

    @property
    def status_display(self):
        return dict(self.STATUSES).get(self.status, self.status)
    @property
    def nr_linii(self):
        return len(self.linii)

    def recalculeaza(self):
        self.subtotal = sum(l.valoare_linie for l in self.linii)
        self.tva_valoare = self.subtotal * self.tva_procent / 100
        self.total = self.subtotal + self.tva_valoare

    def __repr__(self):
        return f'CMD-{self.numar}'

class LinieComanda(db.Model):
    __tablename__ = 'linii_comanda'
    id = db.Column(db.Integer, primary_key=True)
    comanda_id = db.Column(db.Integer, db.ForeignKey('comenzi.id'), nullable=False)
    ordine = db.Column(db.Integer, default=0)
    tip = db.Column(db.String(20), default='Produs')
    cod = db.Column(db.String(100))
    denumire = db.Column(db.String(500))
    dimensiune = db.Column(db.String(100))
    um = db.Column(db.String(20), default='buc')
    cantitate = db.Column(db.Float, default=1)
    pret_unitar = db.Column(db.Float, default=0)
    discount = db.Column(db.Float, default=0)
    _parametri = db.Column('parametri_json', db.Text, default='{}')
    _accesorii = db.Column('accesorii_json', db.Text, default='[]')

    @property
    def parametri(self):
        try: return json.loads(self._parametri or '{}')
        except: return {}
    @parametri.setter
    def parametri(self, v):
        self._parametri = json.dumps(v, ensure_ascii=False)
    @property
    def accesorii(self):
        try: return json.loads(self._accesorii or '[]')
        except: return []
    @accesorii.setter
    def accesorii(self, v):
        self._accesorii = json.dumps(v, ensure_ascii=False)
    @property
    def valoare_linie(self):
        val = self.cantitate * self.pret_unitar
        if self.discount: val -= val * self.discount / 100
        return round(val, 2)

# ═══════════════════════════════════════════════════════════════
# FACTURARE
# ═══════════════════════════════════════════════════════════════

class Factura(db.Model):
    """Invoice - proforma (from Oferta) or fiscal (from Comanda)"""
    __tablename__ = 'facturi'
    TIPURI = [('proforma','Proformă'),('fiscala','Fiscală')]
    STATUSES = [('emisa','Emisă'),('trimisa','Trimisă'),('confirmata','Confirmată'),
                ('incasata','Încasată'),('partial','Parțial Încasată'),('anulata','Anulată')]
    id = db.Column(db.Integer, primary_key=True)
    tip = db.Column(db.String(10), default='fiscala')  # proforma, fiscala
    serie = db.Column(db.String(10), default='HSL')
    numar = db.Column(db.Integer, nullable=False)
    client_id = db.Column(db.Integer, db.ForeignKey('clienti.id'), nullable=False)
    oferta_id = db.Column(db.Integer, db.ForeignKey('oferte.id'), nullable=True)
    comanda_id = db.Column(db.Integer, db.ForeignKey('comenzi.id'), nullable=True)
    status = db.Column(db.String(20), default='emisa')
    data_factura = db.Column(db.Date, default=date.today)
    data_scadenta = db.Column(db.Date)
    subtotal = db.Column(db.Float, default=0)       # RON
    tva_procent = db.Column(db.Float, default=19)
    tva_valoare = db.Column(db.Float, default=0)     # RON
    total = db.Column(db.Float, default=0)           # RON
    moneda = db.Column(db.String(3), default='RON')
    subtotal_eur = db.Column(db.Float, default=0)    # Original EUR
    tva_valoare_eur = db.Column(db.Float, default=0)
    total_eur = db.Column(db.Float, default=0)
    curs_valutar = db.Column(db.Float)               # EUR→RON rate used
    observatii = db.Column(db.Text)
    data_creare = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    linii = db.relationship('LinieFactura', backref='factura', cascade='all, delete-orphan')

    @property
    def numar_complet(self):
        prefix = self.serie or ('PF' if self.tip == 'proforma' else 'HSL')
        return f'{prefix}-{self.numar:06d}'
    
    @property
    def este_platita(self):
        return self.status == 'incasata'
    
    @property
    def este_confirmata(self):
        """Proforma is confirmed (paid or just confirmed by client)"""
        return self.status in ('confirmata', 'incasata')

    def __repr__(self):
        return self.numar_complet

class LinieFactura(db.Model):
    __tablename__ = 'linii_factura'
    id = db.Column(db.Integer, primary_key=True)
    factura_id = db.Column(db.Integer, db.ForeignKey('facturi.id'), nullable=False)
    denumire = db.Column(db.String(500))
    um = db.Column(db.String(20), default='buc')
    cantitate = db.Column(db.Float, default=1)
    pret_unitar = db.Column(db.Float, default=0)
    valoare = db.Column(db.Float, default=0)

# ═══════════════════════════════════════════════════════════════
# ÎNCASĂRI BANCARE
# ═══════════════════════════════════════════════════════════════

class Incasare(db.Model):
    """Bank transaction (payment received)"""
    __tablename__ = 'incasari'
    id = db.Column(db.Integer, primary_key=True)
    # Bank data
    data_tranzactie = db.Column(db.Date, nullable=False)
    suma = db.Column(db.Float, nullable=False)
    moneda = db.Column(db.String(3), default='RON')
    platitor_nume = db.Column(db.String(300))
    platitor_iban = db.Column(db.String(40))
    platitor_cui = db.Column(db.String(20))
    referinta = db.Column(db.String(200))  # payment reference / description
    detalii = db.Column(db.Text)  # full transaction details
    referinta_banca = db.Column(db.String(100), unique=True)  # bank's own transaction ID
    # Reconciliation
    status = db.Column(db.String(20), default='nereconciliat')  # nereconciliat, automat, manual, ignorat
    factura_id = db.Column(db.Integer, db.ForeignKey('facturi.id'), nullable=True)
    factura = db.relationship('Factura', foreign_keys=[factura_id], backref='incasari')
    client_id = db.Column(db.Integer, db.ForeignKey('clienti.id'), nullable=True)
    client = db.relationship('Client', foreign_keys=[client_id])
    reconciliat_de_id = db.Column(db.Integer, db.ForeignKey('utilizatori.id'), nullable=True)
    reconciliat_de = db.relationship('Utilizator', foreign_keys=[reconciliat_de_id])
    data_reconciliere = db.Column(db.DateTime)
    # Metadata
    sursa = db.Column(db.String(20), default='csv')  # csv, api, manual
    data_import = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


# ═══════════════════════════════════════════════════════════════
# WMS - FURNIZORI
# ═══════════════════════════════════════════════════════════════

class Furnizor(db.Model):
    __tablename__ = 'furnizori'
    id = db.Column(db.Integer, primary_key=True)
    nume = db.Column(db.String(200), nullable=False)
    cui = db.Column(db.String(20))
    contact = db.Column(db.String(200))
    telefon = db.Column(db.String(20))
    email = db.Column(db.String(120))
    activ = db.Column(db.Boolean, default=True)
    data_creare = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    def __repr__(self):
        return self.nume


# WMS - CELULE DEPOZIT
# ═══════════════════════════════════════════════════════════════

class CelulaDepozit(db.Model):
    __tablename__ = 'celule_depozit'
    id = db.Column(db.Integer, primary_key=True)
    cod = db.Column(db.String(30), unique=True, nullable=False)  # ex: A-01-03 (zona-raft-nivel)
    zona = db.Column(db.String(30))
    raft = db.Column(db.String(30))
    nivel = db.Column(db.String(30))
    descriere = db.Column(db.String(200))
    barcode = db.Column(db.String(50))  # barcode printed on cell label
    activ = db.Column(db.Boolean, default=True)
    def __repr__(self):
        return self.cod


# WMS - MAPARE CODURI FURNIZOR → COD INTERN
# ═══════════════════════════════════════════════════════════════

class MapareCod(db.Model):
    """Maps supplier codes / EAN codes to internal HSL product codes.
    Builds up over time - first time manual, then auto-suggested."""
    __tablename__ = 'mapari_coduri'
    id = db.Column(db.Integer, primary_key=True)
    furnizor_id = db.Column(db.Integer, db.ForeignKey('furnizori.id'), nullable=True)
    furnizor = db.relationship('Furnizor', backref='mapari')
    cod_furnizor = db.Column(db.String(100))  # supplier internal code (optional)
    cod_ean = db.Column(db.String(20))         # EAN barcode (optional)
    cod_intern = db.Column(db.String(100), nullable=False)  # HSL internal code
    denumire_furnizor = db.Column(db.String(300))  # supplier's product name
    data_creare = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


# WMS - NIR (Nota Intrare-Recepție)
# ═══════════════════════════════════════════════════════════════

class NIR(db.Model):
    """Goods Received Note - created from supplier invoice"""
    __tablename__ = 'niruri'
    STATUSES = [('draft','Draft'),('scriptic','Recepționat Scriptic'),
                ('in_verificare','În Verificare Fizică'),('verificat','Verificat Complet')]
    id = db.Column(db.Integer, primary_key=True)
    numar = db.Column(db.String(50), unique=True, nullable=False)
    furnizor_id = db.Column(db.Integer, db.ForeignKey('furnizori.id'))
    furnizor = db.relationship('Furnizor', backref='niruri')
    numar_factura_furnizor = db.Column(db.String(50))  # supplier invoice number
    data_factura_furnizor = db.Column(db.Date)
    status = db.Column(db.String(20), default='draft')
    data_nir = db.Column(db.Date, default=date.today)
    total_achizitie = db.Column(db.Float, default=0)
    observatii = db.Column(db.Text)
    creat_de_id = db.Column(db.Integer, db.ForeignKey('utilizatori.id'))
    creat_de = db.relationship('Utilizator', foreign_keys=[creat_de_id])
    data_creare = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    linii = db.relationship('LinieNIR', backref='nir', cascade='all, delete-orphan',
                             order_by='LinieNIR.ordine')

    @property
    def status_display(self):
        return dict(self.STATUSES).get(self.status, self.status)

    @property
    def progres_verificare(self):
        """Returns (verified_count, total_count) for physical check progress"""
        total = len(self.linii)
        if not total:
            return 0, 0
        verificate = sum(1 for l in self.linii if l.verificat_complet)
        return verificate, total

    def recalculeaza(self):
        self.total_achizitie = sum(l.valoare_linie for l in self.linii)


class LinieNIR(db.Model):
    __tablename__ = 'linii_nir'
    id = db.Column(db.Integer, primary_key=True)
    nir_id = db.Column(db.Integer, db.ForeignKey('niruri.id'), nullable=False)
    ordine = db.Column(db.Integer, default=0)
    # Supplier codes (all optional)
    cod_furnizor = db.Column(db.String(100))
    cod_ean = db.Column(db.String(20))
    denumire_furnizor = db.Column(db.String(300))
    # Internal mapping
    cod_intern = db.Column(db.String(100), nullable=False)
    denumire_intern = db.Column(db.String(300))
    um = db.Column(db.String(20), default='buc')
    cantitate = db.Column(db.Float, default=1)
    pret_achizitie = db.Column(db.Float, default=0)

    verificari = db.relationship('VerificareNIR', backref='linie_nir', cascade='all, delete-orphan',
                                  order_by='VerificareNIR.data_verificare')

    @property
    def valoare_linie(self):
        return round(self.cantitate * self.pret_achizitie, 2)

    @property
    def cantitate_verificata(self):
        return sum(v.cantitate for v in self.verificari)

    @property
    def verificat_complet(self):
        return self.cantitate_verificata >= self.cantitate

    @property
    def rest_de_verificat(self):
        return max(0, self.cantitate - self.cantitate_verificata)

    @property
    def discrepanta(self):
        """True only when fully done but qty differs"""
        if not self.verificat_complet:
            return False
        return self.cantitate_verificata != self.cantitate


class VerificareNIR(db.Model):
    """Individual physical verification entry for a NIR line.
    Multiple verifications per line to support splitting across cells."""
    __tablename__ = 'verificari_nir'
    id = db.Column(db.Integer, primary_key=True)
    linie_nir_id = db.Column(db.Integer, db.ForeignKey('linii_nir.id'), nullable=False)
    cantitate = db.Column(db.Float, nullable=False)
    celula_id = db.Column(db.Integer, db.ForeignKey('celule_depozit.id'), nullable=True)
    celula = db.relationship('CelulaDepozit')
    verificat_de_id = db.Column(db.Integer, db.ForeignKey('utilizatori.id'))
    verificat_de = db.relationship('Utilizator', foreign_keys=[verificat_de_id])
    data_verificare = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


# WMS - PICKING & LIVRARE
# ═══════════════════════════════════════════════════════════════

class Picking(db.Model):
    """Picking order - preparation for shipping a Comanda"""
    __tablename__ = 'pickings'
    STATUSES = [('nou','Nou'),('in_pregatire','În Pregătire'),('complet','Complet'),('livrat','Livrat'),('anulat','Anulat')]
    id = db.Column(db.Integer, primary_key=True)
    numar = db.Column(db.String(50), unique=True, nullable=False)
    comanda_id = db.Column(db.Integer, db.ForeignKey('comenzi.id'), nullable=False)
    comanda = db.relationship('Comanda', backref=db.backref('pickings', lazy='dynamic'))
    status = db.Column(db.String(20), default='nou')
    observatii = db.Column(db.Text)
    data_creare = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    creat_de_id = db.Column(db.Integer, db.ForeignKey('utilizatori.id'))
    creat_de = db.relationship('Utilizator', foreign_keys=[creat_de_id])
    data_finalizare = db.Column(db.DateTime, nullable=True)

    linii = db.relationship('LiniePicking', backref='picking', cascade='all, delete-orphan',
                             order_by='LiniePicking.ordine')

    @property
    def status_display(self):
        return dict(self.STATUSES).get(self.status, self.status)

    @property
    def progres(self):
        total = len(self.linii)
        if not total: return 0, 0
        preluate = sum(1 for l in self.linii if l.preluata)
        return preluate, total


class LiniePicking(db.Model):
    """Line in a picking order - product to pick from a specific cell"""
    __tablename__ = 'linii_picking'
    id = db.Column(db.Integer, primary_key=True)
    picking_id = db.Column(db.Integer, db.ForeignKey('pickings.id'), nullable=False)
    ordine = db.Column(db.Integer, default=0)
    cod_intern = db.Column(db.String(100), nullable=False)
    denumire = db.Column(db.String(500))
    um = db.Column(db.String(20), default='buc')
    cantitate_ceruta = db.Column(db.Float, default=1)
    # Suggested cell (where stock is)
    celula_sursa_id = db.Column(db.Integer, db.ForeignKey('celule_depozit.id'), nullable=True)
    celula_sursa = db.relationship('CelulaDepozit', foreign_keys=[celula_sursa_id])
    stoc_disponibil = db.Column(db.Float, default=0)  # qty available at time of picking creation
    # Actual pick
    preluata = db.Column(db.Boolean, default=False)
    cantitate_preluata = db.Column(db.Float, default=0)
    celula_efectiva_id = db.Column(db.Integer, db.ForeignKey('celule_depozit.id'), nullable=True)
    celula_efectiva = db.relationship('CelulaDepozit', foreign_keys=[celula_efectiva_id])
    preluat_de_id = db.Column(db.Integer, db.ForeignKey('utilizatori.id'), nullable=True)
    preluat_de = db.relationship('Utilizator', foreign_keys=[preluat_de_id])
    data_preluare = db.Column(db.DateTime, nullable=True)

    @property
    def lipsa(self):
        return max(0, self.cantitate_ceruta - self.stoc_disponibil) if not self.preluata else 0


class NotaLivrare(db.Model):
    """Delivery note - generated after picking is complete"""
    __tablename__ = 'note_livrare'
    id = db.Column(db.Integer, primary_key=True)
    numar = db.Column(db.String(50), unique=True, nullable=False)
    picking_id = db.Column(db.Integer, db.ForeignKey('pickings.id'), nullable=False)
    picking = db.relationship('Picking', backref=db.backref('nota_livrare', uselist=False))
    comanda_id = db.Column(db.Integer, db.ForeignKey('comenzi.id'), nullable=False)
    comanda = db.relationship('Comanda', backref=db.backref('note_livrare', lazy='dynamic'))
    client_id = db.Column(db.Integer, db.ForeignKey('clienti.id'))
    client = db.relationship('Client')
    adresa_livrare = db.Column(db.Text)
    observatii = db.Column(db.Text)
    data_creare = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    creat_de_id = db.Column(db.Integer, db.ForeignKey('utilizatori.id'))
    creat_de = db.relationship('Utilizator', foreign_keys=[creat_de_id])


# WMS - STOC PE LOCAȚIE
# ═══════════════════════════════════════════════════════════════

class StocProdus(db.Model):
    """Current stock per product per location"""
    __tablename__ = 'stoc_produse'
    id = db.Column(db.Integer, primary_key=True)
    cod_intern = db.Column(db.String(100), nullable=False)
    denumire = db.Column(db.String(300))
    celula_id = db.Column(db.Integer, db.ForeignKey('celule_depozit.id'), nullable=True)
    celula = db.relationship('CelulaDepozit')
    cantitate = db.Column(db.Float, default=0)
    pret_achizitie_mediu = db.Column(db.Float, default=0)  # weighted average
    ultima_miscare = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (db.UniqueConstraint('cod_intern', 'celula_id', name='uq_stoc_produs_celula'),)


class StocMinim(db.Model):
    """Minimum stock threshold per product code"""
    __tablename__ = 'stoc_minim'
    id = db.Column(db.Integer, primary_key=True)
    cod_intern = db.Column(db.String(100), unique=True, nullable=False)
    denumire = db.Column(db.String(300))
    prag_minim = db.Column(db.Float, default=0)
    activ = db.Column(db.Boolean, default=True)

    @property
    def stoc_actual(self):
        total = db.session.query(db.func.coalesce(db.func.sum(StocProdus.cantitate), 0)).filter(
            StocProdus.cod_intern == self.cod_intern, StocProdus.celula_id != None
        ).scalar() or 0
        return total

    @property
    def sub_prag(self):
        return self.stoc_actual < self.prag_minim


# WMS - MISCARI STOC (log)
# ═══════════════════════════════════════════════════════════════

class MiscareStoc(db.Model):
    """Stock movement log - all movements for traceability"""
    __tablename__ = 'miscari_stoc'
    TIPURI = [('intrare_nir','Intrare NIR'),('iesire_comanda','Ieșire Comandă'),
              ('transfer','Transfer'),('ajustare','Ajustare'),('inventar','Inventar')]
    id = db.Column(db.Integer, primary_key=True)
    tip = db.Column(db.String(20), nullable=False)
    cod_produs = db.Column(db.String(100))
    denumire_produs = db.Column(db.String(500))
    cantitate = db.Column(db.Float, nullable=False)
    # References
    nir_id = db.Column(db.Integer, db.ForeignKey('niruri.id'), nullable=True)
    comanda_id = db.Column(db.Integer, db.ForeignKey('comenzi.id'), nullable=True)
    celula_id = db.Column(db.Integer, db.ForeignKey('celule_depozit.id'), nullable=True)
    celula = db.relationship('CelulaDepozit', foreign_keys=[celula_id])
    celula_destinatie_id = db.Column(db.Integer, db.ForeignKey('celule_depozit.id'), nullable=True)
    celula_destinatie = db.relationship('CelulaDepozit', foreign_keys=[celula_destinatie_id])
    numar_document = db.Column(db.String(50))
    observatii = db.Column(db.Text)
    utilizator_id = db.Column(db.Integer, db.ForeignKey('utilizatori.id'))
    utilizator = db.relationship('Utilizator', foreign_keys=[utilizator_id])
    data = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    def __repr__(self):
        return f'{self.tip}: {self.cod_produs} ({self.cantitate})'

# ═══════════════════════════════════════════════════════════════
# ACTIVITĂȚI - TIPURI (user-defined)
# ═══════════════════════════════════════════════════════════════

class TipActivitate(db.Model):
    """User-defined activity types"""
    __tablename__ = 'tip_activitati'
    id = db.Column(db.Integer, primary_key=True)
    nume = db.Column(db.String(100), unique=True, nullable=False)
    culoare = db.Column(db.String(20), default='#6c757d')  # hex color for badges
    ordine = db.Column(db.Integer, default=0)
    activ = db.Column(db.Boolean, default=True)
    def __repr__(self):
        return self.nume


# ═══════════════════════════════════════════════════════════════
# ACTIVITĂȚI - ȘABLOANE (templates with triggers)
# ═══════════════════════════════════════════════════════════════

class SablonActivitate(db.Model):
    """Activity template - a group of predefined tasks"""
    __tablename__ = 'sabloane_activitati'
    TRIGGERS = [
        ('manual', 'Manual (aplici de mână)'),
        ('oferta_comanda', 'La convertire Ofertă → Comandă'),
        ('comanda_confirmata', 'La confirmare Comandă'),
        ('comanda_productie', 'La trecere în Producție'),
        ('comanda_livrata', 'La livrare Comandă'),
    ]
    id = db.Column(db.Integer, primary_key=True)
    nume = db.Column(db.String(200), nullable=False)
    descriere = db.Column(db.Text)
    trigger = db.Column(db.String(30), default='manual')
    activ = db.Column(db.Boolean, default=True)
    data_creare = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    linii = db.relationship('LinieSablon', backref='sablon', cascade='all, delete-orphan',
                             order_by='LinieSablon.ordine')

    @property
    def trigger_display(self):
        return dict(self.TRIGGERS).get(self.trigger, self.trigger)

    def aplica(self, comanda_id=None, client_id=None, creat_de_id=None):
        """Generate Activitate instances from this template"""
        created = []
        for linie in self.linii:
            a = Activitate(
                titlu=linie.titlu,
                descriere=linie.descriere,
                tip_id=linie.tip_id,
                prioritate=linie.prioritate,
                ordine=linie.ordine,
                comanda_id=comanda_id,
                client_id=client_id,
                creat_de_id=creat_de_id,
                status='de_facut',
            )
            db.session.add(a)
            created.append(a)
        return created


class LinieSablon(db.Model):
    """Single task line within a template"""
    __tablename__ = 'linii_sabloane'
    id = db.Column(db.Integer, primary_key=True)
    sablon_id = db.Column(db.Integer, db.ForeignKey('sabloane_activitati.id'), nullable=False)
    titlu = db.Column(db.String(200), nullable=False)
    descriere = db.Column(db.Text)
    tip_id = db.Column(db.Integer, db.ForeignKey('tip_activitati.id'), nullable=True)
    tip = db.relationship('TipActivitate')
    prioritate = db.Column(db.String(20), default='normala')
    ordine = db.Column(db.Integer, default=0)


# ═══════════════════════════════════════════════════════════════
# ACTIVITĂȚI (Task/Work Order Management)
# ═══════════════════════════════════════════════════════════════

class Activitate(db.Model):
    """Task/work order - linked to a Comanda or standalone"""
    __tablename__ = 'activitati'
    STATUSES = [('de_facut','De Făcut'),('in_lucru','În Lucru'),('in_asteptare','În Așteptare'),
                ('finalizat','Finalizat'),('anulat','Anulat')]
    PRIORITATI = [('scazuta','Scăzută'),('normala','Normală'),('ridicata','Ridicată'),('urgenta','Urgentă')]

    id = db.Column(db.Integer, primary_key=True)
    titlu = db.Column(db.String(200), nullable=False)
    descriere = db.Column(db.Text)
    tip_id = db.Column(db.Integer, db.ForeignKey('tip_activitati.id'), nullable=True)
    tip_obj = db.relationship('TipActivitate', foreign_keys=[tip_id])
    status = db.Column(db.String(20), default='de_facut')
    prioritate = db.Column(db.String(20), default='normala')
    # Links
    comanda_id = db.Column(db.Integer, db.ForeignKey('comenzi.id'), nullable=True)
    client_id = db.Column(db.Integer, db.ForeignKey('clienti.id'), nullable=True)
    client = db.relationship('Client', foreign_keys=[client_id])
    # Assignment
    asignat_id = db.Column(db.Integer, db.ForeignKey('utilizatori.id'), nullable=True)
    asignat = db.relationship('Utilizator', foreign_keys=[asignat_id], backref='activitati_asignate')
    creat_de_id = db.Column(db.Integer, db.ForeignKey('utilizatori.id'))
    creat_de = db.relationship('Utilizator', foreign_keys=[creat_de_id])
    # Dates
    data_creare = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    deadline = db.Column(db.Date, nullable=True)
    data_start = db.Column(db.DateTime, nullable=True)
    data_finalizare = db.Column(db.DateTime, nullable=True)
    # Ordering
    ordine = db.Column(db.Integer, default=0)

    comentarii = db.relationship('ComentariuActivitate', backref='activitate',
                                  cascade='all, delete-orphan', order_by='ComentariuActivitate.data_creare')

    @property
    def status_display(self):
        return dict(self.STATUSES).get(self.status, self.status)
    @property
    def prioritate_display(self):
        return dict(self.PRIORITATI).get(self.prioritate, self.prioritate)
    @property
    def tip_display(self):
        return self.tip_obj.nume if self.tip_obj else '-'
    @property
    def tip_culoare(self):
        return self.tip_obj.culoare if self.tip_obj else '#6c757d'
    @property
    def is_overdue(self):
        return self.deadline and self.deadline < date.today() and self.status not in ('finalizat','anulat')


class ComentariuActivitate(db.Model):
    """Comment on an Activitate - foundation for chat system"""
    __tablename__ = 'comentarii_activitati'
    id = db.Column(db.Integer, primary_key=True)
    activitate_id = db.Column(db.Integer, db.ForeignKey('activitati.id'), nullable=False)
    utilizator_id = db.Column(db.Integer, db.ForeignKey('utilizatori.id'), nullable=False)
    utilizator = db.relationship('Utilizator', foreign_keys=[utilizator_id])
    mesaj = db.Column(db.Text, nullable=False)
    data_creare = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


# ═══════════════════════════════════════════════════════════════
# SETĂRI
# ═══════════════════════════════════════════════════════════════

class Setari(db.Model):
    __tablename__ = 'setari'
    id = db.Column(db.Integer, primary_key=True)
    cheie = db.Column(db.String(100), unique=True, nullable=False)
    valoare = db.Column(db.Text, default='')

    @classmethod
    def get(cls, cheie, default=''):
        s = cls.query.filter_by(cheie=cheie).first()
        return s.valoare if s else default
    @classmethod
    def set_val(cls, cheie, valoare):
        s = cls.query.filter_by(cheie=cheie).first()
        if s:
            s.valoare = str(valoare)
        else:
            db.session.add(cls(cheie=cheie, valoare=str(valoare)))
        db.session.commit()


# ═══════════════════════════════════════════════════════════════
# AUDIT LOG
# ═══════════════════════════════════════════════════════════════

class AuditLog(db.Model):
    """Audit trail for all document changes"""
    __tablename__ = 'audit_log'
    id = db.Column(db.Integer, primary_key=True)
    tip_document = db.Column(db.String(50), nullable=False)  # oferta, comanda, factura, nir, picking, etc.
    document_id = db.Column(db.Integer, nullable=False)
    document_numar = db.Column(db.String(100))
    actiune = db.Column(db.String(50), nullable=False)  # creat, modificat, status_schimbat, sters
    detalii = db.Column(db.Text)  # JSON or free text description
    utilizator_id = db.Column(db.Integer, db.ForeignKey('utilizatori.id'))
    utilizator = db.relationship('Utilizator', foreign_keys=[utilizator_id])
    data = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    @classmethod
    def log(cls, tip, doc_id, doc_numar, actiune, detalii='', user_id=None):
        entry = cls(tip_document=tip, document_id=doc_id, document_numar=doc_numar,
                    actiune=actiune, detalii=detalii, utilizator_id=user_id)
        db.session.add(entry)

    @classmethod
    def get_for(cls, tip, doc_id, limit=50):
        return cls.query.filter_by(tip_document=tip, document_id=doc_id).order_by(cls.data.desc()).limit(limit).all()


# ═══════════════════════════════════════════════════════════════
# CHAT SYSTEM
# ═══════════════════════════════════════════════════════════════

# Many-to-many: conversation members
chat_members = db.Table('chat_members',
    db.Column('conversatie_id', db.Integer, db.ForeignKey('conversatii.id'), primary_key=True),
    db.Column('utilizator_id', db.Integer, db.ForeignKey('utilizatori.id'), primary_key=True)
)

class Conversatie(db.Model):
    """Chat conversation - direct, group, or document-linked"""
    __tablename__ = 'conversatii'
    TIPURI = [('direct', 'Direct'), ('grup', 'Grup'), ('document', 'Document')]
    id = db.Column(db.Integer, primary_key=True)
    tip = db.Column(db.String(20), default='direct')  # direct, grup, document
    nume = db.Column(db.String(200))  # null for direct, name for group/document
    # Document link (optional)
    doc_tip = db.Column(db.String(50))  # comanda, oferta, etc.
    doc_id = db.Column(db.Integer)
    doc_numar = db.Column(db.String(100))
    # Metadata
    creat_de_id = db.Column(db.Integer, db.ForeignKey('utilizatori.id'))
    creat_de = db.relationship('Utilizator', foreign_keys=[creat_de_id])
    data_creare = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    activ = db.Column(db.Boolean, default=True)

    membri = db.relationship('Utilizator', secondary=chat_members, backref='conversatii_chat')
    mesaje = db.relationship('Mesaj', backref='conversatie', cascade='all, delete-orphan',
                             order_by='Mesaj.data_trimitere')

    @property
    def ultimul_mesaj(self):
        return Mesaj.query.filter_by(conversatie_id=self.id).order_by(Mesaj.data_trimitere.desc()).first()

    @property
    def display_name(self):
        if self.tip == 'document':
            return f'📋 {self.doc_numar or self.doc_tip}'
        if self.tip == 'grup':
            return self.nume or 'Grup'
        return self.nume or 'Conversație'

    def display_name_for(self, user):
        """For direct chats, show the other person's name"""
        if self.tip == 'direct':
            other = [m for m in self.membri if m.id != user.id]
            return other[0].nume_complet if other else 'Conversație'
        return self.display_name

    def necitite_pentru(self, user_id):
        """Count unread messages for a user"""
        return Mesaj.query.filter(
            Mesaj.conversatie_id == self.id,
            Mesaj.autor_id != user_id,
            ~Mesaj.citit_de_ids.contains(f',{user_id},')
        ).count()


class Mesaj(db.Model):
    """Chat message"""
    __tablename__ = 'mesaje'
    id = db.Column(db.Integer, primary_key=True)
    conversatie_id = db.Column(db.Integer, db.ForeignKey('conversatii.id'), nullable=False)
    autor_id = db.Column(db.Integer, db.ForeignKey('utilizatori.id'), nullable=False)
    autor = db.relationship('Utilizator', foreign_keys=[autor_id])
    text = db.Column(db.Text, default='')
    data_trimitere = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    # Reply
    reply_to_id = db.Column(db.Integer, db.ForeignKey('mesaje.id'), nullable=True)
    reply_to = db.relationship('Mesaj', remote_side='Mesaj.id', foreign_keys=[reply_to_id])
    # File attachment
    fisier_nume = db.Column(db.String(300))
    fisier_path = db.Column(db.String(500))
    fisier_size = db.Column(db.Integer)
    fisier_tip = db.Column(db.String(50))
    # Legacy simple tracking
    citit_de_ids = db.Column(db.Text, default=',')

    citiri = db.relationship('MesajCitire', backref='mesaj', cascade='all, delete-orphan')

    def marcat_citit(self, user_id):
        tag = f',{user_id},'
        return tag in (self.citit_de_ids or ',')

    def marcheaza_citit(self, user_id):
        tag = f',{user_id},'
        if tag not in (self.citit_de_ids or ','):
            self.citit_de_ids = (self.citit_de_ids or ',') + f'{user_id},'
            # Add detailed read receipt only if message is already persisted
            if self.id is not None:
                existing = MesajCitire.query.filter_by(mesaj_id=self.id, utilizator_id=user_id).first()
                if not existing:
                    db.session.add(MesajCitire(mesaj_id=self.id, utilizator_id=user_id))


class MesajCitire(db.Model):
    """Read receipt - who read what and when"""
    __tablename__ = 'mesaj_citiri'
    id = db.Column(db.Integer, primary_key=True)
    mesaj_id = db.Column(db.Integer, db.ForeignKey('mesaje.id'), nullable=False)
    utilizator_id = db.Column(db.Integer, db.ForeignKey('utilizatori.id'), nullable=False)
    utilizator = db.relationship('Utilizator', foreign_keys=[utilizator_id])
    data_citire = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (db.UniqueConstraint('mesaj_id', 'utilizator_id'),)


# ════════════════════════════════════════════════════════════
# MAIL INTEGRATION
# ════════════════════════════════════════════════════════════

class ContMail(db.Model):
    """Connected Gmail account (OAuth2)"""
    __tablename__ = 'conturi_mail'
    id = db.Column(db.Integer, primary_key=True)
    utilizator_id = db.Column(db.Integer, db.ForeignKey('utilizatori.id'), nullable=False)
    utilizator = db.relationship('Utilizator', backref='conturi_mail', foreign_keys=[utilizator_id])
    email = db.Column(db.String(200), nullable=False)
    tip = db.Column(db.String(20), default='personal')  # personal, office, monitorizare
    # OAuth2 tokens (encrypted in production)
    access_token = db.Column(db.Text)
    refresh_token = db.Column(db.Text)
    token_expiry = db.Column(db.DateTime)
    # Sync state
    history_id = db.Column(db.String(50))  # Gmail incremental sync
    ultima_sincronizare = db.Column(db.DateTime)
    activ = db.Column(db.Boolean, default=True)
    data_conectare = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    # BCC settings
    bcc_auto = db.Column(db.Text, default='')  # comma-separated emails for auto-BCC


class MailThread(db.Model):
    """Email conversation thread (maps to Gmail thread)"""
    __tablename__ = 'mail_threads'
    id = db.Column(db.Integer, primary_key=True)
    gmail_thread_id = db.Column(db.String(100), index=True)
    cont_mail_id = db.Column(db.Integer, db.ForeignKey('conturi_mail.id'), nullable=False)
    cont_mail = db.relationship('ContMail', backref='threads')
    subiect = db.Column(db.String(500))
    # Assignment
    atribuit_id = db.Column(db.Integer, db.ForeignKey('utilizatori.id'), nullable=True)
    atribuit = db.relationship('Utilizator', foreign_keys=[atribuit_id], backref='mail_atribuite')
    # Auto-linking
    client_id = db.Column(db.Integer, db.ForeignKey('clienti.id'), nullable=True)
    client = db.relationship('Client', foreign_keys=[client_id])
    oferta_id = db.Column(db.Integer, db.ForeignKey('oferte.id'), nullable=True)
    comanda_id = db.Column(db.Integer, db.ForeignKey('comenzi.id'), nullable=True)
    activitate_id = db.Column(db.Integer, db.ForeignKey('activitati.id'), nullable=True)
    # State
    status = db.Column(db.String(20), default='nou')  # nou, atribuit, in_lucru, rezolvat, arhivat
    prioritate = db.Column(db.String(20), default='normala')  # scazuta, normala, ridicata, urgenta
    etichete = db.Column(db.Text, default='')  # comma-separated tags
    # Metadata
    ultimul_mesaj_data = db.Column(db.DateTime)
    ultimul_mesaj_de_la = db.Column(db.String(200))
    nr_mesaje = db.Column(db.Integer, default=0)
    are_atasamente = db.Column(db.Boolean, default=False)
    citit = db.Column(db.Boolean, default=False)
    data_creare = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    mesaje = db.relationship('MailMesaj', backref='thread', cascade='all, delete-orphan',
                             order_by='MailMesaj.data_trimitere')

    __table_args__ = (db.UniqueConstraint('gmail_thread_id', 'cont_mail_id'),)


class MailMesaj(db.Model):
    """Individual email message within a thread"""
    __tablename__ = 'mail_mesaje'
    id = db.Column(db.Integer, primary_key=True)
    thread_id = db.Column(db.Integer, db.ForeignKey('mail_threads.id'), nullable=False)
    gmail_msg_id = db.Column(db.String(100), unique=True, index=True)
    # Headers
    de_la = db.Column(db.String(300))  # From
    de_la_email = db.Column(db.String(200))
    catre = db.Column(db.Text)  # To (comma-separated)
    cc = db.Column(db.Text)
    bcc = db.Column(db.Text)
    subiect = db.Column(db.String(500))
    # Body
    body_text = db.Column(db.Text)
    body_html = db.Column(db.Text)
    # Metadata
    data_trimitere = db.Column(db.DateTime)
    directie = db.Column(db.String(10), default='primit')  # primit, trimis
    snippet = db.Column(db.String(300))
    # Attachments stored as JSON: [{"name": "file.pdf", "size": 1234, "mime": "application/pdf", "gmail_att_id": "..."}]
    _atasamente = db.Column('atasamente', db.Text, default='[]')

    @property
    def atasamente(self):
        import json
        try:
            return json.loads(self._atasamente or '[]')
        except:
            return []

    @atasamente.setter
    def atasamente(self, val):
        import json
        self._atasamente = json.dumps(val)

    @property
    def are_atasamente(self):
        return len(self.atasamente) > 0


# ═══════════════════════════════════════════════════════════════
# CURS VALUTAR
# ═══════════════════════════════════════════════════════════════

class CursValutar(db.Model):
    """Daily exchange rate cache"""
    __tablename__ = 'cursuri_valutare'
    id = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.Date, nullable=False, index=True)
    moneda = db.Column(db.String(3), default='EUR')
    curs_bnr = db.Column(db.Float, nullable=False)
    multiplicator = db.Column(db.Float, default=1.01)  # BNR × 1.01
    curs_final = db.Column(db.Float, nullable=False)
    sursa = db.Column(db.String(20), default='bnr')  # bnr, manual
    data_preluare = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (db.UniqueConstraint('data', 'moneda', name='uq_curs_data_moneda'),)

    def __repr__(self):
        return f'{self.data} {self.moneda}: {self.curs_final:.4f}'
