
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
        return "NON INDICATO"
    t = str(t).replace("&", " e ").replace("<", " ").replace(">", " ").replace('"', " ").replace("'", " ")
    return t.encode("latin-1", "replace").decode("latin-1").upper()

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
        res = supabase.table("contratti").select("numero_fattura").execute()
        nums = [int(r['numero_fattura']) for r in res.data if str(r['numero_fattura']).isdigit()]
        return max(nums) + 1 if nums else 1
    except: return 1

# --- GENERATORE XML (SCORPORO IVA + FIX SCARTI) ---
def genera_xml_sdi(c, forza_straniero=False):
    data_xml = datetime.now().strftime('%Y-%m-%d')
    cf_originale = str(c.get('codice_fiscale', '')).upper().replace(" ", "")
    
    # CALCOLO SCORPORO IVA (Se inserisci 40, l'imponibile diventa 32.79)
    prezzo_totale = float(c.get('prezzo', 0))
    imponibile = round(prezzo_totale / 1.22, 2)
    imposta = round(prezzo_totale - imponibile, 2)

    # GESTIONE ANAGRAFICA PER EVITARE SCARTI
    if forza_straniero or len(cf_originale) != 16:
        # Per gli stranieri usiamo 11 zeri e nazione OO (standard compatibile Aruba/SDI)
        cf_da_inserire = "00000000000" 
        nazione_cliente = "OO"
    else:
        cf_da_inserire = cf_originale
        nazione_cliente = "IT"

    # Validazione CAP e Comune
    cap_cliente = str(c.get('cap', '80075')).strip()
    if not cap_cliente or len(cap_cliente) != 5: cap_cliente = "80075"
    comune_cliente = safe(c.get('comune', 'FORIO'))

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
                <CodiceFiscale>{cf_da_inserire}</CodiceFiscale>
                <Anagrafica><Nome>{safe(c['nome'])}</Nome><Cognome>{safe(c['cognome'])}</Cognome></Anagrafica>
            </DatiAnagrafici>
            <Sede>
                <Indirizzo>{safe(c.get('indirizzo','VIA COGNOLE'))}</Indirizzo>
                <CAP>{cap_cliente}</CAP>
                <Comune>{comune_cliente}</Comune>
                <Provincia>NA</Provincia>
                <Nazione>{nazione_cliente}</Nazione>
            </Sede>
        </CessionarioCommittente>
    </FatturaElettronicaHeader>
    <FatturaElettronicaBody>
        <DatiGenerali><DatiGeneraliDocumento><TipoDocumento>TD01</TipoDocumento><Divisa>EUR</Divisa><Data>{data_xml}</Data><Numero>{c.get('numero_fattura', '1')}</Numero></DatiGeneraliDocumento></DatiGenerali>
        <DatiBeniServizi>
            <DettaglioLinee>
                <NumeroLinea>1</NumeroLinea>
                <Descrizione>Noleggio scooter {c['targa']}</Descrizione>
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

# --- INTERFACCIA (RESTA UGUALE) ---
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
        n, cg, cf = c1.text_input("Nome"), c2.text_input("Cognome"), st.text_input("Codice Fiscale")
        ind, wa = st.text_input("Indirizzo"), st.text_input("WhatsApp")
        com, cap = c1.text_input("Comune", "Forio"), c2.text_input("CAP", "80075")
        tg, mod = c1.text_input("Targa").upper(), c2.text_input("Modello")
        prz = st.number_input("Prezzo TOTALE (IVA inclusa) €", 0.0)
        f1, f2, f3 = st.file_uploader("Patente F"), st.file_uploader("Patente R"), st.file_uploader("Contratto")
        if st.form_submit_button("SALVA CONTRATTO"):
            nf = get_prossimo_numero()
            d = {"nome":n,"cognome":cg,"codice_fiscale":cf,"indirizzo":ind,"comune":com,"cap":cap,"targa":tg,"modello":mod,"prezzo":prz,"pec":wa,"numero_fattura":nf,"data_inizio":datetime.now().strftime("%d/%m/%Y"),"foto_patente":correggi_e_converti_foto(f1),"foto_patente_retro":correggi_e_converti_foto(f2),"firma":correggi_e_converti_foto(f3)}
            supabase.table("contratti").insert(d).execute()
            st.success(f"Archiviato! Fattura n. {nf}")

with t2:
    cerca = st.text_input("🔍 Cerca")
    res = supabase.table("contratti").select("id, nome, cognome, targa, numero_fattura, pec").order("id", desc=True).execute()
    for r in res.data:
        if cerca.lower() in f"{r['targa']} {r['cognome']}".lower():
            with st.expander(f"📄 {r['targa']} - {r['cognome']} ({r['numero_fattura']})"):
                dati = supabase.table("contratti").select("*").eq("id", r['id']).single().execute()
                rc = dati.data
                c_btn = st.columns(3)
                c_btn[0].download_button("📩 XML Standard", genera_xml_sdi(rc), f"Fat_{rc['numero_fattura']}.xml", key=f"s_{r['id']}")
                c_btn[1].download_button("⚠️ Forza XML (Straniero/Fix)", genera_xml_sdi(rc, True), f"Fat_{rc['numero_fattura']}S.xml", key=f"f{r['id']}")
                num_wa = ''.join(filter(str.isdigit, str(rc.get('pec', ''))))
                if num_wa:
                    msg = urllib.parse.quote(f"Ciao {rc['nome']}, grazie da {DITTA}!")
                    c_btn[2].link_button("💬 WhatsApp", f"https://wa.me/{num_wa}?text={msg}")
                st.write("---")
                c_img = st.columns(3)
                mostra_foto_base64(c_img[0], rc.get("foto_patente"), "Fronte")
                mostra_foto_base64(c_img[1], rc.get("foto_patente_retro"), "Retro")
                mostra_foto_base64(c_img[2], rc.get("firma"), "Contratto")

with t3:
    st.subheader("🚨 Sezione Multe")
    targa_m = st.text_input("Targa mezzo").upper()
    if targa_m:
        res = supabase.table("contratti").select("*").eq("targa", targa_m).order("id", desc=True).execute()
        if res.data:
            c = res.data[0]
            st.success(f"Trovato: {c['nome']} {c['cognome']}")
            c1, c2 = st.columns(2)
            com_p, dat_inf = c1.text_input("Comune Polizia"), c2.text_input("Data Infrazione")
            v_n, p_n = c1.text_input("Numero Verbale"), c2.text_input("Protocollo")
            f_v = st.file_uploader("📸 Foto Verbale")
            if st.button("📦 GENERA FASCICOLO"):
                pdf = FPDF()
                pdf.add_page()
                pdf.set_font("Arial", "B", 14)
                pdf.cell(0, 10, "DICHIARAZIONE RINOTIFICA", ln=True, align="C")
                pdf.set_font("Arial", "", 11)
                pdf.multi_cell(0, 10, safe(f"Verbale: {v_n}\nTarga: {targa_m}\nCliente: {c['nome']} {c['cognome']}"))
                st.download_button("📥 Scarica", bytes(pdf.output(dest="S")), f"Multa_{targa_m}.pdf")
