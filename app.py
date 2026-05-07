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

# --- GENERATORE FASCICOLO MULTA (PDF UNIFICATO) ---
def genera_fascicolo_multa(c, v):
    pdf = FPDF()
    # Pagina 1: Rinotifica
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

Si allega copia del contratto e dei documenti di identità (Fronte e Retro)."""
    pdf.multi_cell(0, 7, safe(testo))
    pdf.ln(10)
    pdf.cell(0, 10, "In fede, Marianna Battaglia", align="R")

    # Lista ordinata degli allegati da inserire nel PDF
    allegati = [
        ("foto_patente", "PATENTE FRONTE"),
        ("foto_patente_retro", "PATENTE RETRO"),
        ("firma", "CONTRATTO FIRMATO"),
        ("verbale_multa", "COPIA VERBALE")
    ]
    
    for chiave, titolo in allegati:
        # Se è il verbale lo prendiamo dai dati inseriti ora, altrimenti dal database contratti
        img_str = v.get("img_verbale") if chiave == "verbale_multa" else c.get(chiave)
        
        if img_str and "base64," in img_str:
            try:
                raw_data = img_str.split("base64,")[1]
                img_bytes = base64.b64decode(raw_data)
                
                pdf.add_page()
                pdf.set_font("Arial", "B", 12)
                pdf.cell(0, 10, titolo, ln=True)
                # Inserimento immagine
                pdf.image(io.BytesIO(img_bytes), x=10, w=180)
            except:
                continue # Se una foto ha problemi, passa alla prossima senza bloccare tutto
            
    return bytes(pdf.output(dest="S"))

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
        f1 = st.file_uploader("Patente Fronte")
        f2 = st.file_uploader("Patente Retro")
        f3 = st.file_uploader("Contratto Firmato")
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
                cc1, cc2 = st.columns(2)
                num_wa = ''.join(filter(str.isdigit, str(r.get('pec', ''))))
                cc1.link_button("💬 Chat WhatsApp", f"https://wa.me/{num_wa}")
                
                st.write("---")
                c_img = st.columns(3)
                for i, k in enumerate(["foto_patente", "foto_patente_retro", "firma"]):
                    img_data = r.get(k)
                    if img_data and "base64," in img_data:
                        c_img[i].image(img_data, use_container_width=True)

with t3:
    st.subheader("🚨 Gestione Multe")
    targa_m = st.text_input("Targa mezzo multato").upper()
    col1, col2 = st.columns(2)
    comune_p = col1.text_input("Comune Polizia")
    data_inf = col2.text_input("Data Infrazione")
    verb_n = col1.text_input("Numero Verbale")
    prot_n = col2.text_input("Protocollo")
    f_v = st.file_uploader("Carica Foto Verbale")
    
    if st.button("GENERA FASCICOLO PDF"):
        res = supabase.table("contratti").select("*").eq("targa", targa_m).order("id", desc=True).execute()
        if res.data:
            c = res.data[0]
            v = {"comune":comune_p, "data":data_inf, "num":verb_n, "prot":prot_n, "img_verbale": correggi_e_converti_foto(f_v)}
            try:
                fascicolo = genera_fascicolo_multa(c, v)
                st.download_button("📩 SCARICA FASCICOLO", fascicolo, f"Fascicolo_Multa_{targa_m}.pdf")
            except:
                st.error("Errore nella creazione del PDF. Verifica che i documenti nel contratto siano leggibili.")
        else: st.error("Targa non trovata in archivio!")
