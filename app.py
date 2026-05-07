import streamlit as st
from supabase import create_client, Client
import base64
from datetime import datetime
from fpdf import FPDF
import io
import urllib.parse
from PIL import Image, ImageOps

# --- CONFIGURAZIONE ---
DITTA = "BATTAGLIA RENT"
PIVA = "10252601215"
SEDE_VIA = "Via Cognole n. 5"
SEDE_CAP = "80075"
SEDE_COMUNE = "Forio"
SEDE_PROV = "NA"

URL = st.secrets["SUPABASE_URL"]
KEY = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(URL, KEY)

# --- UTILITY ---
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

# --- PDF MULTE ---
def genera_fascicolo_multa(c, v):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 14)
    pdf.cell(0, 10, "DICHIARAZIONE DI RINOTIFICA", ln=True, align="C")
    pdf.ln(5)
    pdf.set_font("Arial", "", 11)
    testo = f"Al Comando Polizia Locale di {v['comune']}\nOggetto: Rinotifica Verbale n. {v['num']} - Prot. {v['prot']}\n\nLa sottoscritta BATTAGLIA MARIANNA, titolare della ditta {DITTA}, dichiara che il veicolo {c.get('modello','')} targato {c['targa']}, in data {v['data']} era locato a:\n\nCLIENTE: {c['nome'].upper()} {c['cognome'].upper()}\nCF: {c['codice_fiscale'].upper()}\nRESIDENZA: {c.get('indirizzo','')}, {c.get('comune','')} ({c.get('cap','')})\n\nSi allega copia del contratto e dei documenti di identita'."
    pdf.multi_cell(0, 7, safe(testo))
    pdf.ln(10)
    pdf.cell(0, 10, "In fede, Marianna Battaglia", align="R")

    # Allegati
    for chiave, titolo in [("foto_patente","PATENTE F"),("foto_patente_retro","PATENTE R"),("firma","CONTRATTO"),("verbale_multa","VERBALE")]:
        img_str = c.get(chiave) if chiave != "verbale_multa" else v.get("img_verbale")
        if img_str and "base64," in img_str:
            try:
                img_data = base64.b64decode(img_str.split("base64,")[1])
                pdf.add_page()
                pdf.set_font("Arial", "B", 12)
                pdf.cell(0, 10, titolo, ln=True)
                pdf.image(io.BytesIO(img_data), x=10, w=180)
            except: continue
    return bytes(pdf.output(dest="S"))

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

# --- APP ---
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
        n, cg = c1.text_input("Nome"), c2.text_input("Cognome")
        cf = st.text_input("Codice Fiscale")
        ind, wa = st.text_input("Indirizzo"), st.text_input("WhatsApp")
        com, cap = c1.text_input("Comune", "Forio"), c2.text_input("CAP", "80075")
        tg, mod = c1.text_input("Targa").upper(), c2.text_input("Modello")
        prz = st.number_input("Prezzo €", 0.0)
        f1, f2, f3 = st.file_uploader("Patente F"), st.file_uploader("Patente R"), st.file_uploader("Contratto")
        if st.form_submit_button("SALVA"):
            nf = get_prossimo_numero()
            d = {"nome":n,"cognome":cg,"codice_fiscale":cf,"indirizzo":ind,"comune":com,"cap":cap,"targa":tg,"modello":mod,"prezzo":prz,"pec":wa,"numero_fattura":nf,"data_inizio":datetime.now().strftime("%d/%m/%Y"),"foto_patente":correggi_e_converti_foto(f1),"foto_patente_retro":correggi_e_converti_foto(f2),"firma":correggi_e_converti_foto(f3)}
            supabase.table("contratti").insert(d).execute()
            st.success("Archiviato!")

with t2:
    cerca = st.text_input("🔍 Cerca")
    res = supabase.table("contratti").select("*").order("id", desc=True).execute()
    for r in res.data:
        if cerca.lower() in f"{r['targa']} {r['cognome']}".lower():
            with st.expander(f"📄 {r['targa']} - {r['cognome']}"):
                ca, cc = st.columns(2)
                ca.download_button("XML Aruba", genera_xml_sdi(r), f"{r['id']}.xml", key=f"x_{r['id']}")
                num_wa = ''.join(filter(str.isdigit, str(r.get('pec', ''))))
                cc.link_button("Chat WA", f"https://wa.me/{num_wa}")
                st.write("---")
                # VISUALIZZAZIONE FOTO SICURA
                c_img = st.columns(3)
                for i, k in enumerate(["foto_patente", "foto_patente_retro", "firma"]):
                    img_data = r.get(k)
                    if img_data and "base64," in img_data:
                        # Streamlit visualizza direttamente la stringa base64 (MOLTO PIU SICURO)
                        c_img[i].image(img_data, use_container_width=True)
                    else:
                        c_img[i].info("Mancante")

with t3:
    st.subheader("🚨 Gestione Multe")
    targa_m = st.text_input("Targa mezzo").upper()
    col1, col2 = st.columns(2)
    comune_p = col1.text_input("Comune Polizia")
    data_inf = col2.text_input("Data Infrazione")
    verb_n = col1.text_input("Numero Verbale")
    prot_n = col2.text_input("Protocollo")
    f_v = st.file_uploader("Foto Verbale")
    
    if st.button("GENERA FASCICOLO"):
        res = supabase.table("contratti").select("*").eq("targa", targa_m).order("id", desc=True).execute()
        if res.data:
            c = res.data[0]
            v = {"comune":comune_p, "data":data_inf, "num":verb_n, "prot":prot_n, "img_verbale": correggi_e_converti_foto(f_v)}
            try:
                fascicolo = genera_fascicolo_multa(c, v)
                st.download_button("📩 SCARICA PDF", fascicolo, f"Fascicolo_{targa_m}.pdf")
            except Exception as e:
                st.error("Errore PDF. Alcune foto potrebbero essere troppo grandi o danneggiate.")
        else: st.error("Targa non trovata!")
