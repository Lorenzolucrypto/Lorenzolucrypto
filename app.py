
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
        return "DATO ASSENTE"
    # Pulizia caratteri per XML SDI
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

def get_prossimo_numero():
    try:
        # Cerca il numero più alto nel database per suggerire il prossimo
        res = supabase.table("contratti").select("numero_fattura").order("numero_fattura", desc=True).limit(1).execute()
        if res.data:
            ultimo_num = int(res.data[0]['numero_fattura'])
            return ultimo_num + 1
        return 1
    except: return 1

# --- GENERATORE XML (SCORPORO IVA + ANTI-SCARTO) ---
def genera_xml_sdi(c, forza_straniero=False):
    data_xml = datetime.now().strftime('%Y-%m-%d')
    cf_originale = str(c.get('codice_fiscale', '')).upper().replace(" ", "")
    
    # SCORPORO IVA (Tu inserisci il totale, lui calcola l'imponibile)
    prezzo_totale = float(c.get('prezzo', 0))
    imponibile = round(prezzo_totale / 1.22, 2)
    imposta = round(prezzo_totale - imponibile, 2)

    # GESTIONE DATI CLIENTE
    if forza_straniero:
        # Modalità emergenza: Cliente Estero (OO) con 11 zeri
        cf_blocco = "<CodiceFiscale>00000000000</CodiceFiscale>"
        nazione_blocco = "OO"
        cap_blocco = "00000"
    elif len(cf_originale) == 16:
        # Italiano standard
        cf_blocco = f"<CodiceFiscale>{cf_originale}</CodiceFiscale>"
        nazione_blocco = "IT"
        cap_blocco = str(c.get('cap', '80075'))[:5]
    else:
        # Fallback se il CF è incompleto
        cf_blocco = "<CodiceFiscale>00000000000</CodiceFiscale>"
        nazione_blocco = "OO"
        cap_blocco = "00000"

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

# --- INTERFACCIA STREAMLIT ---
st.set_page_config(page_title="BATTAGLIA RENT", layout="centered")
if "auth" not in st.session_state: st.session_state.auth = False
if not st.session_state.auth:
    pwd = st.text_input("Password", type="password")
    if st.button("ACCEDI"):
        if pwd == "1234": st.session_state.auth = True; st.rerun()
    st.stop()

t1, t2, t3 = st.tabs(["📝 NUOVO CONTRATTO", "📂 ARCHIVIO", "🚨 MULTE"])

with t1:
    with st.form("f"):
        c1, c2 = st.columns(2)
        n, cg, cf = c1.text_input("Nome"), c2.text_input("Cognome"), st.text_input("Codice Fiscale")
        ind, wa = st.text_input("Indirizzo"), st.text_input("WhatsApp (es. 39333...)")
        com, cap = c1.text_input("Comune", "Forio"), c2.text_input("CAP", "80075")
        tg, mod = c1.text_input("Targa").upper(), c2.text_input("Modello")
        prz = st.number_input("Prezzo Totale Incassato €", 0.0)
        f1, f2, f3 = st.file_uploader("Patente Fronte"), st.file_uploader("Patente Retro"), st.file_uploader("Contratto Firmato")
        if st.form_submit_button("💾 SALVA E GENERA NUMERO"):
            nf = get_prossimo_numero()
            d = {"nome":n,"cognome":cg,"codice_fiscale":cf,"indirizzo":ind,"comune":com,"cap":cap,"targa":tg,"modello":mod,"prezzo":prz,"pec":wa,"numero_fattura":nf,"data_inizio":datetime.now().strftime("%d/%m/%Y"),"foto_patente":correggi_e_converti_foto(f1),"foto_patente_retro":correggi_e_converti_foto(f2),"firma":correggi_e_converti_foto(f3)}
            supabase.table("contratti").insert(d).execute()
            st.success(f"Contratto salvato con Fattura n. {nf}")

with t2:
    cerca = st.text_input("🔍 Cerca per targa o cognome")
    res = supabase.table("contratti").select("id, nome, cognome, targa, numero_fattura, pec").order("numero_fattura", desc=True).execute()
    for r in res.data:
        if cerca.lower() in f"{r['targa']} {r['cognome']}".lower():
            with st.expander(f"📄 Fattura {r['numero_fattura']} - {r['targa']} ({r['cognome']})"):
                dati = supabase.table("contratti").select("*").eq("id", r['id']).single().execute()
                rc = dati.data
                bt1, bt2 = st.columns(2)
                bt1.download_button("📩 Scarica XML", genera_xml_sdi(rc), f"Fat_{rc['numero_fattura']}.xml", key=f"s_{r['id']}")
                bt2.download_button("🚨 FIX (Se Aruba dà errore)", genera_xml_sdi(rc, True), f"Fat_{rc['numero_fattura']}FIX.xml", key=f"f{r['id']}")
                
                wa_link = ''.join(filter(str.isdigit, str(rc.get('pec', ''))))
                if wa_link:
                    st.link_button("💬 Invia Messaggio WhatsApp", f"https://wa.me/{wa_link}")

with t3:
    st.subheader("🚨 Gestione Multe")
    t_multe = st.text_input("Inserisci targa per rinotifica").upper()
    if t_multe:
        r_m = supabase.table("contratti").select("*").eq("targa", t_multe).order("id", desc=True).limit(1).execute()
        if r_m.data:
            m = r_m.data[0]
            st.info(f"Veicolo associato a: {m['nome']} {m['cognome']}")
            if st.button("📄 Genera Dichiarazione"):
                st.write("Funzione in fase di stampa...")
