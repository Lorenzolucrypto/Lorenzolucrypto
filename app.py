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
    if t is None or str(t).strip() == "" or str(t).lower() == "none": 
        return "DATO MANCANTE"
    t = str(t).replace("&", " e ").replace("<", " ").replace(">", " ").replace('"', " ").replace("'", " ")
    return t.encode("ascii", "ignore").decode("ascii").upper()

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

def mostra_foto_base64(colonna, base64_str, titolo=""):
    if base64_str and "base64," in base64_str:
        try:
            img_data = base64.b64decode(base64_str.split("base64,")[1])
            colonna.image(img_data, caption=titolo, use_container_width=True)
        except:
            colonna.error(f"Errore {titolo}")
    else:
        colonna.info(f"{titolo} assente")

def get_prossimo_numero():
    try:
        res = supabase.table("contratti").select("numero_fattura").order("numero_fattura", desc=True).limit(1).execute()
        if res.data: return int(res.data[0]['numero_fattura']) + 1
        return 1
    except: return 1

# --- GENERATORE XML ---
def genera_xml_sdi(c, forza_straniero=False):
    data_xml = datetime.now().strftime('%Y-%m-%d')
    cf_originale = str(c.get('codice_fiscale', '')).upper().replace(" ", "")
    prezzo_totale = float(c.get('prezzo', 0) if c.get('prezzo') is not None else 0)
    imponibile = round(prezzo_totale / 1.22, 2)
    imposta = round(prezzo_totale - imponibile, 2)

    if forza_straniero or len(cf_originale) != 16:
        cf_blocco, nazione_blocco, cap_blocco = "<CodiceFiscale>00000000000</CodiceFiscale>", "OO", "00000"
    else:
        cf_blocco, nazione_blocco, cap_blocco = f"<CodiceFiscale>{cf_originale}</CodiceFiscale>", "IT", str(c.get('cap', '80075'))[:5]

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<p:FatturaElettronica versione="FPR12" xmlns:p="http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.2">
    <FatturaElettronicaHeader>
        <DatiTrasmissione>
            <IdTrasmittente><IdPaese>IT</IdPaese><IdCodice>01879020517</IdCodice></IdTrasmittente>
            <ProgressivoInvio>{c.get('numero_fattura', '1')}</ProgressivoInvio>
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
            <DatiAnagrafici>
                {cf_blocco}
                <Anagrafica><Nome>{safe(c.get('nome', ''))}</Nome><Cognome>{safe(c.get('cognome', ''))}</Cognome></Anagrafica>
            </DatiAnagrafici>
            <Sede><Indirizzo>{safe(c.get('indirizzo','VIA COGNOLE'))}</Indirizzo><CAP>{cap_blocco}</CAP><Comune>{safe(c.get('comune','FORIO'))}</Comune><Nazione>{nazione_blocco}</Nazione></Sede>
        </CessionarioCommittente>
    </FatturaElettronicaHeader>
    <FatturaElettronicaBody>
        <DatiGenerali><DatiGeneraliDocumento><TipoDocumento>TD01</TipoDocumento><Divisa>EUR</Divisa><Data>{data_xml}</Data><Numero>{c.get('numero_fattura', '1')}</Numero></DatiGeneraliDocumento></DatiGenerali>
        <DatiBeniServizi>
            <DettaglioLinee><NumeroLinea>1</NumeroLinea><Descrizione>Noleggio scooter {c.get('targa', 'NA')}</Descrizione><PrezzoUnitario>{imponibile:.2f}</PrezzoUnitario><PrezzoTotale>{imponibile:.2f}</PrezzoTotale><AliquotaIVA>22.00</AliquotaIVA></DettaglioLinee>
            <DatiRiepilogo><AliquotaIVA>22.00</AliquotaIVA><ImponibileImporto>{imponibile:.2f}</ImponibileImporto><Imposta>{imposta:.2f}</Imposta><EsigibilitaIVA>I</EsigibilitaIVA></DatiRiepilogo>
        </DatiBeniServizi>
    </FatturaElettronicaBody>
</p:FatturaElettronica>""".encode('utf-8')

# --- GENERATORE PDF MULTA ---
def genera_pdf_multe(contratto, v_n, p_n, com_p, data_inf, foto_verbale):
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    pdf.add_page()
    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 10, "COMUNICAZIONE DATI CONDUCENTE / RINOTIFICA", ln=True, align="C")
    pdf.ln(10)
    
    pdf.set_font("Arial", "B", 12)
    pdf.cell(0, 10, "DATI VERBALE:", ln=True)
    pdf.set_font("Arial", "", 12)
    pdf.multi_cell(0, 8, f"Verbale N: {v_n}\nProtocollo: {p_n}\nComune: {com_p}\nData Infrazione: {data_inf}")
    pdf.ln(5)
    
    pdf.set_font("Arial", "B", 12)
    pdf.cell(0, 10, "DATI NOLEGGIATORE (BATTAGLIA RENT):", ln=True)
    pdf.set_font("Arial", "", 12)
    pdf.multi_cell(0, 8, f"Targa Veicolo: {contratto.get('targa', 'NON INDICATA')}\nModello: {contratto.get('modello', 'NON INDICATO')}")
    pdf.ln(5)

    pdf.set_font("Arial", "B", 12)
    pdf.cell(0, 10, "DATI CONDUCENTE:", ln=True)
    pdf.set_font("Arial", "", 12)
    pdf.multi_cell(0, 8, f"Nome e Cognome: {contratto.get('nome', '')} {contratto.get('cognome', '')}\nCodice Fiscale: {contratto.get('codice_fiscale', '')}\nIndirizzo: {contratto.get('indirizzo', '')}, {contratto.get('comune', '')} ({contratto.get('cap', '')})")
    
    def add_b64_img(b64_str, titolo):
        if b64_str and "base64," in b64_str:
            try:
                pdf.add_page()
                pdf.set_font("Arial", "B", 12)
                pdf.cell(0, 10, titolo, ln=True)
                header, data = b64_str.split("base64,")
                img_data = base64.b64decode(data)
                img_io = io.BytesIO(img_data)
                pdf.image(img_io, x=10, y=30, w=180)
            except: pass

    add_b64_img(contratto.get("foto_patente"), "PATENTE FRONTE")
    add_b64_img(contratto.get("foto_patente_retro"), "PATENTE RETRO")
    add_b64_img(contratto.get("firma"), "CONTRATTO FIRMATO")
    
    if foto_verbale:
        try:
            pdf.add_page()
            pdf.set_font("Arial", "B", 12)
            pdf.cell(0, 10, "FOTO VERBALE", ln=True)
            pdf.image(foto_verbale, x=10, y=30, w=180)
        except: pass

    return pdf.output(dest="S").encode("latin-1", "replace")

# --- INTERFACCIA ---
st.set_page_config(page_title="BATTAGLIA RENT", layout="centered")

if "auth" not in st.session_state: 
    st.session_state.auth = False

if not st.session_state.auth:
    pwd = st.text_input("Password", type="password")
    if st.button("ACCEDI"):
        if pwd == "1234": 
            st.session_state.auth = True
            st.rerun()
    st.stop()

t1, t2, t3 = st.tabs(["📝 NUOVO", "📂 ARCHIVIO", "🚨 MULTE"])

with t1:
    with st.form("f", clear_on_submit=False):
        c1, c2 = st.columns(2)
        n, cg, cf = c1.text_input("Nome"), c2.text_input("Cognome"), st.text_input("Codice Fiscale")
        ind, wa = st.text_input("Indirizzo"), st.text_input("WhatsApp")
        c3, c4 = st.columns(2)
        com, cap = c3.text_input("Comune", "Forio"), c4.text_input("CAP", "80075")
        tg, mod = c3.text_input("Targa").upper(), c4.text_input("Modello")
        prz = st.number_input("Totale €", 0.0)
        f1, f2, f3 = st.file_uploader("Patente F"), st.file_uploader("Patente R"), st.file_uploader("Contratto")
        
        if st.form_submit_button("💾 SALVA"):
            nf = get_prossimo_numero()
            d = {"nome":n,"cognome":cg,"codice_fiscale":cf,"indirizzo":ind,"comune":com,"cap":cap,"targa":tg,"modello":mod,"prezzo":prz,"pec":wa,"numero_fattura":nf,"data_inizio":datetime.now().strftime("%d/%m/%Y"),"foto_patente":correggi_e_converti_foto(f1),"foto_patente_retro":correggi_e_converti_foto(f2),"firma":correggi_e_converti_foto(f3)}
            supabase.table("contratti").insert(d).execute()
            st.success(f"Salvato con successo! Fattura n. {nf}")

with t2:
    cerca = st.text_input("🔍 Cerca")
    res = supabase.table("contratti").select("*").order("numero_fattura", desc=True).execute()
    for rc in res.data:
        # PROTEZIONE CASI VUOTI: usiamo .get() con fallback a stringa vuota per evitare il crash
        targa_sicura = str(rc.get('targa', '')) if rc.get('targa') is not None else ''
        cognome_sicuro = str(rc.get('cognome', '')) if rc.get('cognome') is not None else ''
        
        if cerca.lower() in f"{targa_sicura} {cognome_sicuro}".lower():
            with st.expander(f"📄 Fat. {rc.get('numero_fattura', 'N/D')} - {rc.get('nome', '')} {cognome_sicuro} ({targa_sicura})"):
                b1, b2 = st.columns(2)
                b1.download_button("📩 XML", genera_xml_sdi(rc), f"Fat_{rc.get('numero_fattura', '1')}.xml", key=f"xml_std_{rc['id']}")
                b2.download_button("🚨 FIX", genera_xml_sdi(rc, True), f"Fat_{rc.get('numero_fattura', '1')}FIX.xml", key=f"xml_fix{rc['id']}")
                
                st.write(f"*Indirizzo:* {rc.get('indirizzo','')}, {rc.get('comune','')} ({rc.get('cap','')})")
                st.write(f"*Codice Fiscale:* {rc.get('codice_fiscale','')}")
                
                num_wa = ''.join(filter(str.isdigit, str(rc.get('pec', ''))))
                if num_wa: st.link_button("💬 WhatsApp", f"https://wa.me/{num_wa}")
                
                st.write("---")
                c_img = st.columns(3)
                mostra_foto_base64(c_img[0], rc.get("foto_patente"), "Patente F")
                mostra_foto_base64(c_img[1], rc.get("foto_patente_retro"), "Patente R")
                mostra_foto_base64(c_img[2], rc.get("firma"), "Contratto")

with t3:
    st.subheader("🚨 Gestione Multe / Rinotifiche")
    targa_m = st.text_input("Inserisci Targa per trovare il cliente").upper()
    if targa_m:
        res = supabase.table("contratti").select("*").eq("targa", targa_m).order("numero_fattura", desc=True).limit(1).execute()
        if res.data:
            c = res.data[0]
            st.success(f"Ultimo noleggio trovato: {c.get('nome', '')} {c.get('cognome', '')} (Fattura {c.get('numero_fattura', 'N/D')})")
            with st.form("form_multa"):
                col1, col2 = st.columns(2)
                v_num = col1.text_input("Numero Verbale")
                p_num = col2.text_input("Protocollo")
                com_pol = col1.text_input("Comune/Comando Polizia")
                data_i = col2.text_input("Data Infrazione")
                f_verbale = st.file_uploader("📸 Foto del Verbale ricevuto")
                if st.form_submit_button("📦 GENERA PDF COMPLETO"):
                    pdf_bytes = genera_pdf_multe(c, v_num, p_num, com_pol, data_i, f_verbale)
                    st.download_button("📥 Scarica Fascicolo Multa", pdf_bytes, f"Multa_{targa_m}{v_num}.pdf", key=f"dl_multa{c['id']}")
        else:
            st.warning("Nessun contratto trovato per questa targa.")
