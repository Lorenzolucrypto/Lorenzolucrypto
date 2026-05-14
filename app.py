
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
            colonna.error(f"Errore caricamento {titolo}")
    else:
        colonna.info(f"{titolo} non presente")

def get_prossimo_numero():
    try:
        res = supabase.table("contratti").select("numero_fattura").order("numero_fattura", desc=True).limit(1).execute()
        if res.data:
            return int(res.data[0]['numero_fattura']) + 1
        return 1
    except: return 1

# --- GENERATORE XML ---
def genera_xml_sdi(c, forza_straniero=False):
    data_xml = datetime.now().strftime('%Y-%m-%d')
    cf_originale = str(c.get('codice_fiscale', '')).upper().replace(" ", "")
    prezzo_totale = float(c.get('prezzo', 0))
    imponibile = round(prezzo_totale / 1.22, 2)
    imposta = round(prezzo_totale - imponibile, 2)

    if forza_straniero or len(cf_originale) != 16:
        cf_blocco = "<CodiceFiscale>00000000000</CodiceFiscale>"
        nazione_blocco = "OO"
        cap_blocco = "00000"
    else:
        cf_blocco = f"<CodiceFiscale>{cf_originale}</CodiceFiscale>"
        nazione_blocco = "IT"
        cap_blocco = str(c.get('cap', '80075'))[:5]

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
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
                <Anagrafica><Nome>{safe(c['nome'])}</Nome><Cognome>{safe(c['cognome'])}</Cognome></Anagrafica>
            </DatiAnagrafici>
            <Sede>
                <Indirizzo>{safe(c.get('indirizzo','VIA COGNOLE'))}</Indirizzo>
                <CAP>{cap_blocco}</CAP>
                <Comune>{safe(c.get('comune','FORIO'))}</Comune>
                <Nazione>{nazione_blocco}</Nazione>
            </Sede>
        </CessionarioCommittente>
    </FatturaElettronicaHeader>
    <FatturaElettronicaBody>
        <DatiGenerali><DatiGeneraliDocumento><TipoDocumento>TD01</TipoDocumento><Divisa>EUR</Divisa><Data>{data_xml}</Data><Numero>{c.get('numero_fattura', '1')}</Numero></DatiGeneraliDocumento></DatiGenerali>
        <DatiBeniServizi>
            <DettaglioLinee>
                <NumeroLinea>1</NumeroLinea>
                <Descrizione>Noleggio scooter {c.get('targa', 'NA')}</Descrizione>
                <PrezzoUnitario>{imponibile:.2f}</PrezzoUnitario>
                <PrezzoTotale>{imponibile:.2f}</PrezzoTotale>
                <AliquotaIVA>22.00</AliquotaIVA>
            </DettaglioLinee>
            <DatiRiepilogo>
                <AliquotaIVA>22.00</AliquotaIVA>
                <ImponibileImporto>{imponibile:.2f}</ImponibileImporto>
                <Imposta>{imposta:.2f}</Imposta>
                <EsigibilitaIVA>I</EsigibilitaIVA>
            </DatiRiepilogo>
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
        n = c1.text_input("Nome")
        cg = c2.text_input("Cognome")
        cf = st.text_input("Codice Fiscale")
        ind = st.text_input("Indirizzo di residenza")
        c3, c4 = st.columns(2)
        com = c3.text_input("Comune", "Forio")
        cap = c4.text_input("CAP", "80075")
        wa = st.text_input("Numero WhatsApp (per invio contratto)")
        st.write("---")
        c5, c6 = st.columns(2)
        tg = c5.text_input("Targa").upper()
        mod = c6.text_input("Modello Scooter")
        prz = st.number_input("Totale Incassato € (IVA inclusa)", 0.0)
        st.write("---")
        f1 = st.file_uploader("Foto Patente Fronte")
        f2 = st.file_uploader("Foto Patente Retro")
        f3 = st.file_uploader("Foto Contratto Firmato")
        
        if st.form_submit_button("💾 SALVA CONTRATTO"):
            nf = get_prossimo_numero()
            d = {"nome":n,"cognome":cg,"codice_fiscale":cf,"indirizzo":ind,"comune":com,"cap":cap,"targa":tg,"modello":mod,"prezzo":prz,"pec":wa,"numero_fattura":nf,"data_inizio":datetime.now().strftime("%d/%m/%Y"),"foto_patente":correggi_e_converti_foto(f1),"foto_patente_retro":correggi_e_converti_foto(f2),"firma":correggi_e_converti_foto(f3)}
            supabase.table("contratti").insert(d).execute()
            st.success(f"Salvato con successo! Numero fattura assegnato: {nf}")

with t2:
    cerca = st.text_input("🔍 Cerca per targa o cognome")
    res = supabase.table("contratti").select("id, nome, cognome, targa, numero_fattura, pec").order("numero_fattura", desc=True).execute()
    for r in res.data:
        if cerca.lower() in f"{r['targa']} {r['cognome']}".lower():
            with st.expander(f"📄 Fattura {r['numero_fattura']} - {r['nome']} {r['cognome']} ({r['targa']})"):
                # Recupero tutti i dati per le foto
                dati = supabase.table("contratti").select("*").eq("id", r['id']).single().execute()
                rc = dati.data
                
                col_btn1, col_btn2 = st.columns(2)
                col_btn1.download_button("📩 XML Standard", genera_xml_sdi(rc), f"Fat_{rc['numero_fattura']}.xml", key=f"s_{r['id']}")
                col_btn2.download_button("🚨 XML FIX (Emergenza)", genera_xml_sdi(rc, True), f"Fat_{rc['numero_fattura']}FIX.xml", key=f"f{r['id']}")
                
                st.write(f"*Indirizzo:* {rc.get('indirizzo','')}, {rc.get('comune','')} ({rc.get('cap','')})")
                st.write(f"*Codice Fiscale:* {rc.get('codice_fiscale','')}")
                
                num_wa = ''.join(filter(str.isdigit, str(rc.get('pec', ''))))
                if num_wa:
                    st.link_button("💬 WhatsApp", f"https://wa.me/{num_wa}")
                
                st.write("---")
                # Sezione Foto
                st.subheader("Immagini caricate")
                c_img = st.columns(3)
                mostra_foto_base64(c_img[0], rc.get("foto_patente"), "Patente Fronte")
                mostra_foto_base64(c_img[1], rc.get("foto_patente_retro"), "Patente Retro")
                mostra_foto_base64(c_img[2], rc.get("firma"), "Contratto Firmato")

with t3:
    st.subheader("🚨 Gestione Multe")
    t_multe = st.text_input("Targa per rinotifica").upper()
    if t_multe:
        r_m = supabase.table("contratti").select("*").eq("targa", t_multe).order("numero_fattura", desc=True).limit(1).execute()
        if r_m.data:
            m = r_m.data[0]
            st.success(f"Trovato ultimo cliente: {m['nome']} {m['cognome']}")
