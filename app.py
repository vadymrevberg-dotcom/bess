import os
import json
import uuid
import requests
import pandas as pd
import streamlit as st
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
from openai import OpenAI

# Импорты твоих модулей
from src.analytics import simulate_without_battery_30d, simulate_with_battery_30d, compute_waiting_cost
from src.report import generate_pdf_report
from src.load_profile import load_consumption_profile

# --- ИНФРАСТРУКТУРА ---
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY") 
ai_client = OpenAI(api_key=OPENAI_API_KEY)

CSV_PATH = "data/output.csv"
EFFICIENCY = 0.9
PV_KWH_PER_KWP_DAY = 3.0

PV_PROFILE = pd.Series(
    [0, 0, 0, 0, 0, 0.02, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.32, 0.30, 0.25, 0.20, 0.15, 0.10, 0.05, 0.02, 0, 0, 0, 0],
    index=range(24)
)

st.set_page_config(page_title="Niezależny Audytor OZE", layout="centered", page_icon="⚡")

# --- L2 ADMIN: EXEKUCJA DANYCH ---
st.sidebar.subheader("🔒 Admin: Zabezpieczenie Aktywów")
st.sidebar.markdown("Pobierz stare dane przed resetem serwera.")
if st.sidebar.button("Pobierz lokalne CSV"):
    if os.path.exists("data/beta_testers.csv"):
        with open("data/beta_testers.csv", "rb") as f:
            st.sidebar.download_button("Pobierz e-maile (CSV)", f, "beta_testers_backup.csv")
    else:
        st.sidebar.error("Brak pliku beta_testers.csv")
        
    if os.path.exists("data/oferty_raport.csv"):
        with open("data/oferty_raport.csv", "rb") as f2:
            st.sidebar.download_button("Pobierz oferty (CSV)", f2, "oferty_raport_backup.csv")

# ==========================================
# KONFIGURACJA ZEWNĘTRZNA (Telegram + SMTP)
# ==========================================
TG_TOKEN = os.environ.get("TG_TOKEN")
TG_CHAT_ID = os.environ.get("TG_CHAT_ID")

def send_email_with_pdf(receiver_email, pdf_path):
    sender_email = os.environ.get("GMAIL_USER")
    sender_password = os.environ.get("GMAIL_PASS")
    if not sender_email or not sender_password:
        raise Exception("Brak konfiguracji SMTP (GMAIL_USER/GMAIL_PASS w Secrets)")

    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = receiver_email
    msg['Subject'] = "⚡ Twój Niezależny Audyt OZE (Raport)"

    body = "Cześć,\n\nW załączniku przesyłamy Twój niezależny audyt opłacalności instalacji.\nDokument zawiera inżynieryjne wyliczenia (symulację zysków na taryfach RCE) oraz argumenty do negocjacji z instalatorem, które pomogą Ci zbić cenę.\n\nPozdrawiamy,\nNiezależny System Weryfikacji OZE"
    msg.attach(MIMEText(body, 'plain'))

    with open(pdf_path, "rb") as attachment:
        part = MIMEBase('application', 'octet-stream')
        part.set_payload(attachment.read())

    encoders.encode_base64(part)
    part.add_header('Content-Disposition', f"attachment; filename=Audyt_OZE.pdf")
    msg.attach(part)

    server = smtplib.SMTP('smtp.gmail.com', 587)
    server.starttls()
    server.login(sender_email, sender_password)
    server.send_message(msg)
    server.quit()

@st.cache_data
def load_data():
    df = pd.read_csv(CSV_PATH)
    if "hour" in df.columns and df["hour"].max() > 23:
        df["hour"] = df["hour"] - 1
    df = df[df["hour"].between(0, 23)]
    return df

try:
    df = load_data()
    available_dates = sorted(df["date"].unique())
    last_30_dates = available_dates[-30:] if len(available_dates) >= 30 else available_dates
    df_30d = df[df["date"].isin(last_30_dates)]
    target_date = last_30_dates[-1]
    day_prices = df[df["date"] == target_date].set_index("hour").sort_index()
except FileNotFoundError:
    st.error("Błąd: Brak pliku data/output.csv. Zaktualizuj dane ENTSO-E.")
    st.stop()

st.title("⚡ Niezależny Ekspert OZE")
st.markdown("Weryfikujemy rynek. Sprawdź, czy Twoja oferta jest uczciwa, lub wylicz od zera, czego potrzebujesz, aby nie tracić na taryfach dynamicznych.")
st.markdown("*Niezależny projekt inżynieryjny. Nie sprzedajemy paneli, walczymy z marżą 30%.*")

tab1, tab2 = st.tabs(["🕵️‍♂️ Sprawdź Ofertę (Weryfikator)", "🤖 Kalkulator Strat (Od zera)"])

# ==========================================================
# TAB 1: АНАЛИЗАТОР ОФЕРТЫ (TEASER GATING & JSON)
# ==========================================================
with tab1:
    st.subheader("Weryfikator wycen od instalatorów")
    st.markdown("Dostałeś ofertę? Wpisz jej parametry. Algorytm sprawdzi ukrytą marżę na bazie cen hurtowych.")
    
    col_o1, col_o2 = st.columns(2)
    with col_o1:
        oferta_cena = st.number_input("Cena całkowita brutto (PLN):", min_value=0, max_value=200000, value=0, step=1000)
        oferta_pv = st.number_input("Moc fotowoltaiki z oferty (kWp):", min_value=0.0, max_value=50.0, value=0.0, step=0.5)
    with col_o2:
        oferta_bess = st.number_input("Pojemność magazynu z oferty (kWh):", min_value=0.0, max_value=50.0, value=0.0, step=1.0)
        oferta_sprzet = st.text_input("Marki sprzętu (Falownik, Panele):", placeholder="np. Deye, panele Jinko 450W")
        
    if st.button("🔍 Prześwietl moją ofertę"):
        if oferta_cena == 0 or oferta_pv == 0.0:
            st.error("⚠️ Wprowadź realną cenę i moc instalacji, aby algorytm mógł zadziałać.")
        else:
            with st.spinner("Skanowanie bazy cen hurtowych i weryfikacja podzespołów..."):
                
                # Zapisz w pamięci (Most do Tab 2)
                st.session_state.pv_from_tab1 = oferta_pv
                st.session_state.bess_from_tab1 = oferta_bess

                # L3: Twarda matematyka w Pythonie
                if oferta_bess > 0:
                    min_total = (oferta_pv * 4000) + (oferta_bess * 1500)
                    max_total = (oferta_pv * 5500) + (oferta_bess * 2500)
                else:
                    min_total = oferta_pv * 3000
                    max_total = oferta_pv * 3800

                if oferta_cena > max_total:
                    stan_oferty = f"OFERTA ZAWYŻONA. Klient przepłaca od {oferta_cena - max_total:.0f} do {oferta_cena - min_total:.0f} PLN w stosunku do realnych cen hurtowych i uczciwej marży."
                elif oferta_cena < min_total:
                    stan_oferty = f"OFERTA PODEJRZANIE TANIA. Cena jest o {min_total - oferta_cena:.0f} PLN niższa od rynkowego minimum. Gigantyczne ryzyko cięcia kosztów na zabezpieczeniach."
                else:
                    stan_oferty = "OFERTA UCZCIWA. Cena mieści się w rynkowych widełkach dla tego roku."

                roast_prompt = f"""
                Jesteś zimnym, analitycznym inżynierem audytorem OZE. Brak empatii, brak języka sprzedażowego. Tylko brutalne, techniczne fakty.
                
                Sprzęt zaproponowany klientowi: {oferta_sprzet}
                Wynik matematycznej weryfikacji cen (TWARDE DANE - NIE ZMIENIAJ ICH):
                {stan_oferty}
                
                ZADANIE: Wygeneruj odpowiedź w formacie JSON zawierającą dwa klucze: "teaser" oraz "pdf_roast".
                
                "teaser": Krótkie 2 zdania. Oceń klasę podanego sprzętu i zacytuj wynik matematyczny. Ton: suchy raport. 
                "pdf_roast": 4 twarde punkty z argumentami do negocjacji/weryfikacji dla klienta. Uderz w wady sprzętu, wymuś sprawdzenie grubości kabli, zabezpieczeń.
                """
                
                try:
                    response = ai_client.chat.completions.create(
                        model="gpt-4o-mini",
                        response_format={ "type": "json_object" },
                        messages=[{"role": "user", "content": roast_prompt}],
                        temperature=0.1
                    )

                    # Parsowanie JSON z AI
                    wynik_json = json.loads(response.choices[0].message.content)
                    teaser = wynik_json.get("teaser", "Zidentyfikowano sprzęt. Analiza gotowa.")
                    pdf_roast = wynik_json.get("pdf_roast", "Brak szczegółów sprzętowych.")

                    # L3 PATCH: Sanityzacja danych JSON (Sklejanie listy w string)
                    if isinstance(pdf_roast, list):
                        pdf_roast = "\n".join([f"• {item}" for item in pdf_roast])
                    elif isinstance(pdf_roast, str):
                        pdf_roast = pdf_roast.strip()

                    # Zapisujemy twarde argumenty dla PDF
                    st.session_state.ai_roast = str(pdf_roast)

                    # Ekran: Suchy, analityczny teaser
                    st.warning("⚠️ **WSTĘPNY WERDYKT SYSTEMU:**")
                    st.markdown(teaser)
                    
                    st.error("🔒 **SZCZEGÓŁOWY RAPORT I ARGUMENTY DO NEGOCJACJI UKRYTE**")
                    st.info(
                        "Aby otrzymać pełną, inżynieryjną analizę błędów w tej ofercie, przejdź do zakładki **🤖 Kalkulator Strat (na samej górze)**. \n\n"
                        "Wpisz swój rachunek za prąd, a system wygeneruje twardy, 2-stronicowy raport PDF na Twój adres e-mail."
                    )
                    
                    with open("data/oferty_raport.csv", "a", encoding="utf-8") as f:
                        f.write(f"{oferta_cena},{oferta_pv},{oferta_bess},{oferta_sprzet}\n")
                    
                    tg_msg = f"🕵️‍♂️ ROAST OFERTY:\nCena: {oferta_cena} PLN\nPV: {oferta_pv} kWp\nBESS: {oferta_bess} kWh\nSprzęt: {oferta_sprzet}\nWerdykt: {stan_oferty}"
                    try:
                        requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", data={"chat_id": TG_CHAT_ID, "text": tg_msg}, timeout=3)
                    except Exception:
                        pass

                except Exception as e:
                    st.error(f"Błąd analizy AI. Sprawdź logi serwera: {e}")

# ==========================================================
# TAB 2: КАЛЬКУЛЯТОР С НУЛЯ (HARD GATE - SMTP PDF)
# ==========================================================
with tab2:
    if "calculated" not in st.session_state:
        st.session_state.calculated = False
    if "ai_params" not in st.session_state:
        st.session_state.ai_params = {}
    if "financials" not in st.session_state:
        st.session_state.financials = {}

    st.markdown("Oblicz opłacalność inwestycji na taryfach dynamicznych RCE. **Jeśli sprawdziłeś już swoją ofertę w zakładce obok, system automatycznie pobierze z niej moce (kWp i kWh).**")

    col1, col2 = st.columns(2)
    with col1:
        rachunek = st.number_input("Miesięczny rachunek za prąd (PLN):", min_value=100, max_value=5000, value=400, step=50, key="r_calc")
        miasto = st.text_input("Miasto / Kod pocztowy:", value="Wrocław", key="m_calc")
    with col2:
        ogrzewanie = st.selectbox("Czym ogrzewasz dom?", ["Pompa ciepła", "Kocioł gazowy / Pellet", "Ogrzewanie elektryczne", "Węgiel / Drewno"], key="o_calc")
        dach = st.selectbox("Rodzaj dachu:", ["Skośny - blacha", "Skośny - dachówka", "Płaski"], key="d_calc")

    if st.button("🤖 Oblicz opłacalność (ROI)"):
        with st.spinner("System pobiera ceny giełdowe ENTSO-E i wylicza oszczędności..."):
            
            # Most pomiędzy zakładkami
            pv_rule = f"Użyj DOKŁADNIE pv_kwp = {st.session_state.pv_from_tab1}" if "pv_from_tab1" in st.session_state else "Dobierz optymalną moc PV (kWp)"
            bess_rule = f"Użyj DOKŁADNIE battery_kwh = {st.session_state.bess_from_tab1}" if "bess_from_tab1" in st.session_state else "Dobierz optymalną pojemność magazynu (kWh)"

            prompt = f"""
            Jesteś inżynierem OZE. Klient płaci {rachunek} PLN/mc. Ogrzewanie: {ogrzewanie}. 
            Oszacuj zużycie roczne w kWh. 
            {pv_rule}.
            {bess_rule}.
            Profil: "G12" jeśli pompa ciepła/elektryczne, inaczej "G11".
            ZWRÓĆ TYLKO JSON: {{"annual_kwh": int, "pv_kwp": float, "battery_kwh": float, "profile": string}}
            """
            
            try:
                response = ai_client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1
                )
                ai_data = json.loads(response.choices[0].message.content.replace('```json', '').replace('```', '').strip())
                st.session_state.ai_params = ai_data
            except Exception as e:
                st.error("Błąd tłumaczenia AI.")
                st.stop()

            # --- MATH ENTSO-E ---
            annual_kwh = ai_data["annual_kwh"]
            pv_kwp = ai_data["pv_kwp"]
            battery_kwh = ai_data["battery_kwh"]
            profile_name = ai_data["profile"]
            
            try:
                consumption = load_consumption_profile(profile_name=profile_name, annual_kwh=annual_kwh).loc[day_prices.index]
            except Exception as e:
                consumption = load_consumption_profile(profile_name="G11", annual_kwh=annual_kwh).loc[day_prices.index]

            pv_generation = PV_PROFILE * pv_kwp * PV_KWH_PER_KWP_DAY
            pv_generation = pv_generation.loc[day_prices.index]
            self_consumed = consumption.clip(upper=pv_generation)
            remaining_consumption = consumption - self_consumed
            pv_excess = pv_generation - self_consumed

            battery_charge_from_pv = min(pv_excess.sum(), battery_kwh)
            
            if remaining_consumption.sum() > 0 and battery_charge_from_pv > 0:
                battery_used = (remaining_consumption / remaining_consumption.sum()) * battery_charge_from_pv
                grid_consumption = remaining_consumption - battery_used
            else:
                grid_consumption = remaining_consumption

            num_days = len(last_30_dates)
            cost_no_battery_period = simulate_without_battery_30d(df_30d, remaining_consumption, 0.45)
            cost_pv_battery_period = simulate_without_battery_30d(df_30d, grid_consumption, 0.45)

            available_for_arbitrage = max(0, battery_kwh - battery_charge_from_pv)
            arbitrage_profit_period = simulate_with_battery_30d(df_30d, grid_consumption, available_for_arbitrage, EFFICIENCY, 0.45)

            cost_with_battery_period = cost_pv_battery_period - arbitrage_profit_period
            profit_battery_period = cost_no_battery_period - cost_with_battery_period

            st.session_state.financials = {
                "pv_generation": pv_generation,
                "consumption": consumption,
                "cost_no_battery_daily": cost_no_battery_period / num_days,
                "cost_with_battery_daily": cost_with_battery_period / num_days,
                "profit_battery_daily": profit_battery_period / num_days,
                "waiting_cost": compute_waiting_cost(profit_battery_period / num_days, 6)
            }
            st.session_state.calculated = True

    if st.session_state.calculated:
        p = st.session_state.ai_params
        f = st.session_state.financials
        
        st.success(f"**Przeanalizowano system:** Fotowoltaika {p['pv_kwp']} kWp + Magazyn {p['battery_kwh']} kWh")
        col_a, col_b, col_c = st.columns(3)
        col_a.metric("Twój profil", p['profile'])
        col_b.metric("Zysk dzienny z BESS", f"{f['profit_battery_daily']:.2f} PLN")
        col_c.error(f"🔴 KOSZT ZWŁOKI (6 m-cy): {f['waiting_cost']:.2f} PLN")

        st.write("---")
        st.subheader("📩 Odbierz Pełny Raport PDF na e-mail")
        st.markdown(
          "Generujemy twarde dane, z którymi pójdziesz na negocjacje. Weryfikujemy Twój e-mail, aby wyeliminować fałszywe zapytania od instalatorów.\n\n"
          "🛡️ *Gwarantujemy brak spamu i brak telefonów od handlowców. Jesteśmy niezależnym narzędziem inżynieryjnym.*"
        )

        contact_email = st.text_input("Na jaki e-mail wysłać wyliczenia?")
        if st.button("Wyślij mi darmowy Audyt PDF"):
            if "@" in contact_email and "." in contact_email:
                with st.spinner("Generowanie inżynieryjnego raportu i wysyłka na e-mail..."):
                    chart_data = {
                        "hours": list(range(24)),
                        "pv_kw": f['pv_generation'].tolist(),
                        "cons_kw": f['consumption'].tolist(),
                        "prices": day_prices["price_pln_mwh"].tolist(),
                        "cheap_hours": day_prices["price_pln_mwh"].nsmallest(3).index.tolist(),
                        "expensive_hours": day_prices["price_pln_mwh"].nlargest(3).index.tolist()
                    }
                    
                    # L3 PATCH: Pobieranie pełnego werdyktu AI do PDF
                    ai_roast_text = st.session_state.get("ai_roast", "Kalkulacja wykonana od zera. Brak parametrów z oferty instalatora do weryfikacji.")
                    
                    output_pdf = f"data/audyt_{uuid.uuid4().hex[:8]}.pdf"
                    generate_pdf_report(
                        output_path=output_pdf, client={"city": miasto, "annual_kwh": p['annual_kwh'], "battery_kwh": p['battery_kwh'], "profile": p['profile'], "pv_kwp": p['pv_kwp']},
                        date=target_date, cost_no_battery=f['cost_no_battery_daily'], cost_with_battery=f['cost_with_battery_daily'],
                        profit_daily=f['profit_battery_daily'], waiting_cost=f['waiting_cost'], chart_data=chart_data,
                        ai_roast=ai_roast_text
                    )
                    
                    try:
                        # WYSYŁKA EMAIL
                        send_email_with_pdf(contact_email, output_pdf)
                        
                        # Zapis lokalny i Telegram (tylko w przypadku sukcesu)
                        with open("data/beta_testers.csv", "a", encoding="utf-8") as file_csv:
                            file_csv.write(f"{miasto},{p['pv_kwp']},{p['battery_kwh']},{contact_email}\n")

                        tg_msg_lead = f"⚡ NOWY LEAD (EMAIL ZWERYFIKOWANY)!\nMiasto: {miasto}\nPV: {p['pv_kwp']} kWp\nBESS: {p['battery_kwh']} kWh\nEmail: {contact_email}"
                        try:
                            requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", data={"chat_id": TG_CHAT_ID, "text": tg_msg_lead}, timeout=3)
                        except Exception:
                            pass
                        
                        st.success("✅ Sukces! Raport został wysłany. Sprawdź swoją skrzynkę (oraz folder SPAM).")
                    except Exception as e:
                        st.error(f"❌ Błąd wysyłki. Serwer pocztowy nie odpowiada. Spróbuj ponownie później.")
            else:
                st.error("Wprowadź poprawny adres e-mail.")
