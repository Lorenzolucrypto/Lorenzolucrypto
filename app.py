import streamlit as st
from supabase import create_client, Client
import base64
from datetime import datetime
from fpdf import FPDF
import io
import urllib.parse
from PIL import Image, ImageOps

# --- CONFIGURAZIONE BATTAGLIA RENT ---
DITTA = "BATTAGLIA RENT"
PIVA = "10252601215"
SEDE_VIA = "Via Cognole n. 5"
SEDE_CAP = "80075"
SEDE_COMUNE = "Forio"
SEDE_PROV = "NA"

# Connessione Database
URL = st.secrets["SUPABASE_URL"]
KEY = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(URL, KEY)

# --- FUNZIONI DI UTILITÀ ---
def safe(t): 
    return str(t).encode("latin-1", "replace").decode("latin-1")

def correggi_e_converti_foto(image_file):
    if image_file is not None:
        try:
            img = Image.open(image_file)
            img = ImageOps.exif_transpose(img)
            buffered = io.BytesIO()
            img.save(buffered, format="JPEG", quality=70)
            return "data:image/jpeg;base64," + base64.b64encode(buffered.getvalue()).decode()
        except Exception: return None
    return None

def get_prossimo_numero():
    try:
        res = supabase.table("contratti").select("numero_fattura").execute()
        nums = [int(r['numero_fattura']) for r in res.data if str(r['numero_fattura']).isdigit()]
        return max(nums) + 1 if nums else 1
    except: return 1

# --- GENERATORE FASCICOLO MULTA (PDF UNIFICATO) ---
def genera_fascicolo_multa(c, v):
    pdf = FPDF()
    # Pag 1: Rinotifica
    pdf.add_page()
    pdf.set_font("Arial", "B", 14)
    pdf.cell(0, 10, "DICHIARAZIONE DI RINOTIFICA", ln=True, align="C")
    pdf.ln(5)
    pdf.set_font("Arial", "", 11)
    testo = f"""Al Comando Polizia Locale di {v['comune']}
Oggetto: Rinotifica Verbale n. {v['num']} - Prot. {v['prot']}

La sottoscritta BATTAGLIA MARIANNA, titolare della ditta {DITTA}, dichiara che il veicolo {c.get('modello','')} 
targato {c['targa']}, in data {v['data']} era locato a:

CLIENTE: {c['nome'].upper()} {c['cognome'].upper()}
CF: {c['codice_fiscale'].upper()}
RESIDENZA: {c.get('indirizzo','')}, {c.get('comune','')} ({c.get('cap','')})

Si allega copia del contratto e dei documenti."""
    pdf.multi_cell(0, 7, safe(testo))
    pdf.ln(10)
    pdf.cell(0, 10, "Firma: ________________________", align="R")

    # Pagine Allegati (Patente, Contratto, Verbale)
    foto_da_aggiungere = [
        ("foto_patente", "PATENTE FRONTE"),
        ("foto_patente_retro", "PATENTE RETRO"),
        ("firma", "CONTRATTO FIRMATO"),
        ("verbale_multa", "COPIA VERBALE")
    ]
    
    for chiave, titolo in foto_da_aggiungere:
        img_str = c.get(chiave) if chiave != "verbale_multa" else v.get("img_verbale")
        if img_str and "base64," in img_str:
            pdf.add_page()
            pdf.set_font("Arial", "B", 12)
            pdf.cell(0, 10, titolo, ln=True)
            img_data = base64.b64decode(img_str.split("base64,")[1])
            pdf.image(io.BytesIO(img_data), x=10, w=180)
            
    return bytes(pdf.output(dest="S"))

# --- ALTRE FUNZIONI PDF/XML (Cortesia e Aruba) ---
def genera_xml_sdi(c):
    data_xml = datetime.now().strftime('%Y-%m-%d')
    cf = "00000000000" if c['codice_fiscale'] == "XXXXXXXXXXXXXXXX" else c['codice_fiscale']
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<p:FatturaElettronica versione="FPR12" xmlns:p="http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.2">
    <FatturaElettronicaHeader>
        <DatiTrasmissione>
            <IdTrasmittente><IdPaese>IT</IdPaese><IdCodice>01879020517</IdCodice></IdTrasmittente>
            <ProgressivoInvio>{c['numero_fattura']}</ProgressivoInvio>
            <FormatoTrasmissione>FPR12</FormatoTrasmissione>
            <CodiceDestinatario>0000000</CodiceDestinatario>
        </DatiTrasmissione>
        <CedentePrestatore>
            <DatiAnagrafici>
                <IdFiscaleIVA><IdPaese>IT</IdPaese><IdCodice>{PIVA}</IdCodice></IdFiscaleIVA>
                <Anagrafica><Denominazione>{DITTA}</Denominazione></Anagrafica>
                <RegimeFiscale>RF19</RegimeFiscale>
            </DatiAnagrafici>
            <Sede><Indirizzo>{SEDE_VIA}</Indirizzo><CAP>{SEDE_CAP}</CAP><Comune>{SEDE_COMUNE}</Comune><Provincia>{SEDE_PROV}</Provincia><Nazione>IT</Nazione></Sede>
        </CedentePrestatore>
        <CessionarioCommittente>
            <DatiAnagrafici><CodiceFiscale>{cf}</CodiceFiscale><Anagrafica><Nome>{c['nome']}</Nome><Cognome>{c['cognome']}</Cognome></Anagrafica></DatiAnagrafici>
            <Sede><Indirizzo>{c.get('indirizzo','')}</Indirizzo><CAP>{c.get('cap','80075')}</CAP><Comune>{c.get('comune','Forio')}</Comune><Provincia>NA</Provincia><Nazione>IT</Nazione></Sede>
        </CessionarioCommittente>
    </FatturaElettronicaHeader>
    <FatturaElettronicaBody>
        <DatiGenerali><DatiGeneraliDocumento><TipoDocumento>TD01</TipoDocumento><Divisa>EUR</Divisa><Data>{data_xml}</Data><Numero>{c['numero_fattura']}</Numero></DatiGeneraliDocumento></DatiGenerali>
        <DatiBeniServizi>
            <DettaglioLinee><NumeroLinea>1</NumeroLinea><Descrizione>Noleggio scooter {c['targa']}</Descrizione><PrezzoUnitario>{c['prezzo']:.2f}</PrezzoUnitario><PrezzoTotale>{c['prezzo']:.2f}</PrezzoTotale><AliquotaIVA>22.00</AliquotaIVA></DettaglioLinee>
            <DatiRiepilogo><AliquotaIVA>22.00</AliquotaIVA><ImponibileImporto>{c['prezzo']:.2f}</ImponibileImporto><Imposta>{(c['prezzo']*0.22):.2f}</Imposta></DatiRiepilogo>
        </DatiBeniServizi>
    </FatturaElettronicaBody>
</p:FatturaElettronica>"""
    return xml.encode('utf-8')

# --- INTERFACCIA ---
st.set_page_config(page_title="BATTAGLIA RENT", layout="centered")

if "auth" not in st.session_state: st.session_state.auth = False
if not st.session_state.auth:
    pwd = st.text_input("Password", type="password")
    if st.button("ACCEDI"):
        if pwd == "1234": st.session_state.auth = True; st.rerun()
    st.stop()

t1, t2, t3 = st.tabs(["📝 NUOVO", "📂 ARCHIVIO", "🚨 MULTE"])

with t1:
    with st.form("f"):
        c1, c2 = st.columns(2)
        nome, cognome = c1.text_input("Nome"), c2.text_input("Cognome")
        cf = st.text_input("Codice Fiscale")
        ind, wa = st.text_input("Indirizzo"), st.text_input("WhatsApp")
        com, cap = c1.text_input("Comune", "Forio"), c2.text_input("CAP", "80075")
        tg, mod = c1.text_input("Targa").upper(), c2.text_input("Modello")
        prezzo = st.number_input("Prezzo €", 0.0)
        f_p1 = st.file_uploader("Patente Fronte")
        f_p2 = st.file_uploader("Patente Retro")
        f_cnt = st.file_uploader("Contratto Firmato")
        if st.form_submit_button("SALVA"):
            nf = get_prossimo_numero()
            d = {"nome":nome,"cognome":cognome,"codice_fiscale":cf,"indirizzo":ind,"comune":com,"cap":cap,"targa":tg,"modello":mod,"prezzo":prezzo,"pec":wa,"numero_fattura":nf,"data_inizio":datetime.now().strftime("%d/%m/%Y"),"foto_patente":correggi_e_converti_foto(f_p1),"foto_patente_retro":correggi_e_converti_foto(f_p2),"firma":correggi_e_converti_foto(f_cnt)}
            supabase.table("contratti").insert(d).execute()
            st.success("Salvato!")

with t2:
    cerca = st.text_input("Cerca")
    res = supabase.table("contratti").select("*").order("id", desc=True).execute()
    for r in res.data:
        if cerca.lower() in f"{r['targa']} {r['cognome']}".lower():
            with st.expander(f"{r['targa']} - {r['cognome']}"):
                ca, cb, cc = st.columns(3)
                ca.download_button("XML Aruba", genera_xml_sdi(r), f"{r['id']}.xml")
                cc.link_button("Chat WA", f"https://wa.me/{r['pec']}")
                # Visualizzazione foto
                i1, i2, i3 = st.columns(3)
                for k, col, lab in [("foto_patente",i1,"F"),("foto_patente_retro",i2,"R"),("firma",i3,"C")]:
                    if r.get(k): col.image(base64.b64decode(r[k].split(",")[1]), caption=lab)

with t3:
    st.subheader("🚨 Gestione Multe Professionale")
    targa_m = st.text_input("Targa del mezzo multato").upper()
    col1, col2 = st.columns(2)
    comune_p = col1.text_input("Comune Polizia")
    data_inf = col2.text_input("Data Infrazione")
    verb_n = col1.text_input("Numero Verbale")
    prot_n = col2.text_input("Protocollo")
    f_verbale = st.file_uploader("Carica Foto/Scansione Verbale")
    
    if st.button("GENERA FASCICOLO COMPLETO"):
        res = supabase.table("contratti").select("*").eq("targa", targa_m).order("id", desc=True).execute()
        if res.data:
            c = res.data[0]
            v = {"comune":comune_p, "data":data_inf, "num":verb_n, "prot":prot_n, "img_verbale": correggi_e_converti_foto(f_verbale)}
            fascicolo = genera_fascicolo_multa(c, v)
            st.download_button("📩 SCARICA FASCICOLO (PDF UNICO)", fascicolo, f"Multa_{targa_m}.pdf")
            st.info("Il PDF contiene: Rinotifica + Patente + Contratto + Verbale.")
        else: st.error("Targa non trovata!")
