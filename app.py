import os
import json
import uuid
import requests
import pandas as pd
import streamlit as st
from openai import OpenAI

# Импорты твоих модулей
from src.analytics import simulate_without_battery_30d, simulate_with_battery_30d, compute_waiting_cost
from src.report import generate_pdf_report
from src.load_profile import load_consumption_profile

# --- ИНФРАСТРУКТУРА ---
# ВНИМАНИЕ: Замени свой засвеченный ключ на новый в переменных окружения!
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
# TELEGRAM KONFIGURACJA (WPISZ SWOJE DANE!)
# ==========================================
TG_TOKEN = os.environ.get("TG_TOKEN")
TG_CHAT_ID = os.environ.get("TG_CHAT_ID")          # np. "123456789"

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

tab1, tab2 = st.tabs(["🕵️‍♂️ Sprawdź Ofertę (Weryfikator)", "🤖 Kalkulator Strat (Od zera)"])

# ==========================================================
# TAB 1: АНАЛИЗАТОР ОФЕРТЫ (ROAST MY QUOTE)
# ==========================================================
with tab1:
    st.subheader("Weryfikator wycen od instalatorów")
    st.markdown("Dostałeś ofertę? Wpisz jej parametry poniżej. Sprawdź, czy nie przepłacasz i czy sprzęt jest wysokiej jakości.")
    
    col_o1, col_o2 = st.columns(2)
    with col_o1:
        oferta_cena = st.number_input("Cena całkowita brutto (PLN):", min_value=1000, max_value=200000, value=45000, step=1000)
        oferta_pv = st.number_input("Moc fotowoltaiki z oferty (kWp):", min_value=1.0, max_value=50.0, value=8.0, step=0.5)
    with col_o2:
        oferta_bess = st.number_input("Pojemność magazynu z oferty (kWh):", min_value=0.0, max_value=50.0, value=10.0, step=1.0)
        oferta_sprzet = st.text_input("Marki sprzętu (Falownik, Panele):", placeholder="np. FoxESS, panele Jinko 450W")
        
    if st.button("🔍 Prześwietl moją ofertę"):
        with st.spinner("Analizujemy cenniki rynkowe i jakość podzespołów..."):
            
            # L2 PATCH: Dynamiczna wycena zależna od architektury (Hybryda vs On-Grid)
            if oferta_bess > 0:
                pv_price_rule = "- Średnia uczciwa cena PV (falownik hybrydowy + montaż + zabezpieczenia): 4000 - 5500 PLN brutto za 1 kWp."
                bess_rule = "- Średnia uczciwa cena magazynu (LiFePO4 + BMS): 1500 - 2500 PLN brutto za 1 kWh."
                system_type = "Instalacja Hybrydowa (PV + Magazyn)"
            else:
                pv_price_rule = "- Średnia uczciwa cena PV (zwykły falownik sieciowy/stringowy + montaż): 3000 - 3800 PLN brutto za 1 kWp. UWAGA: Ceny powyżej 4000 PLN/kWp dla czystej instalacji bez magazynu w 2026 roku są mocno zawyżone!"
                bess_rule = "- Klient nie wycenia magazynu energii (0 kWh)."
                system_type = "Zwykła Instalacja PV (On-Grid, bez magazynu)"

            roast_prompt = f"""
            Jesteś niezależnym inżynierem OZE w Polsce, chroniącym klientów przed naciągaczami.
            Klient dostał ofertę:
            - Typ systemu: {system_type}
            - Cena całkowita: {oferta_cena} PLN brutto
            - Fotowoltaika: {oferta_pv} kWp
            - Magazyn: {oferta_bess} kWh
            - Proponowany sprzęt: {oferta_sprzet}

            TWARDE REGUŁY RYNKOWE W POLSCE (MARZEC 2026):
            {pv_price_rule}
            {bess_rule}
            - UWAGA: Cena może być o 10-15% niższa od średniej, jeśli firma mocno optymalizuje koszty operacyjne (np. mała ekipa lokalna). Nie odrzucaj z automatu tanich ofert, jeśli matematyka się spina z dolnymi widełkami.
            - Sprzęt Premium: Huawei, BYD, Fronius, SolarEdge, Victron.
            - Sprzęt Standard: Deye, FoxESS, SolaX, Pylontech.
            - Sprzęt Budżetowy: Growatt, Sofar, GoodWe.

            Zadanie:
            1. Oceń uczciwość ceny całkowitej na podstawie powyższych widełek dla konkretnego typu systemu. Pokaż matematykę.
            2. Oceń klasę sprzętu.
            3. Daj inżynieryjną radę: "Podpisz", "Negocjuj" lub "Odrzuć ofertę".
            """
            
            try:
                response = ai_client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": roast_prompt}],
                    temperature=0.2
                )

                st.info("💡 **Werdykt:**")
                st.markdown(response.choices[0].message.content)
                
                # Zapis lokalny
                with open("data/oferty_raport.csv", "a", encoding="utf-8") as f:
                    f.write(f"{oferta_cena},{oferta_pv},{oferta_bess},{oferta_sprzet}\n")
                
                # WYSYŁKA DO TELEGRAM
                tg_msg = f"🕵️‍♂️ ROAST OFERTY:\nCena: {oferta_cena} PLN\nPV: {oferta_pv} kWp\nBESS: {oferta_bess} kWh\nSprzęt: {oferta_sprzet}"
                try:
                    requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", data={"chat_id": TG_CHAT_ID, "text": tg_msg}, timeout=3)
                except Exception:
                    pass

            except Exception as e:
                st.error(f"Błąd analizy: {e}")

# ==========================================================
# TAB 2: КАЛЬКУЛЯТОР С НУЛЯ (ENTSO-E PIPELINE)
# ==========================================================
with tab2:
    if "calculated" not in st.session_state:
        st.session_state.calculated = False
    if "ai_params" not in st.session_state:
        st.session_state.ai_params = {}
    if "financials" not in st.session_state:
        st.session_state.financials = {}

    col1, col2 = st.columns(2)
    with col1:
        rachunek = st.number_input("Miesięczny rachunek za prąd (PLN):", min_value=100, max_value=5000, value=400, step=50, key="r_calc")
        miasto = st.text_input("Miasto / Kod pocztowy:", value="Wrocław", key="m_calc")
    with col2:
        ogrzewanie = st.selectbox("Czym ogrzewasz dom?", ["Pompa ciepła", "Kocioł gazowy / Pellet", "Ogrzewanie elektryczne", "Węgiel / Drewno"], key="o_calc")
        dach = st.selectbox("Rodzaj dachu:", ["Skośny - blacha", "Skośny - dachówka", "Płaski"], key="d_calc")

    if st.button("🤖 Oblicz moje straty i dobierz sprzęt"):
        with st.spinner("System pobiera ceny giełdowe ENTSO-E..."):
            prompt = f"""
            Jesteś inżynierem OZE. Klient płaci {rachunek} PLN/mc. Ogrzewanie: {ogrzewanie}. 
            Oszacuj zużycie roczne w kWh. Dobierz optymalną moc PV (kWp) i magazynu (kWh).
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
        
        st.success(f"**Twój optymalny zestaw:** Fotowoltaika {p['pv_kwp']} kWp + Magazyn {p['battery_kwh']} kWh")
        col_a, col_b, col_c = st.columns(3)
        col_a.metric("Twój profil", p['profile'])
        col_b.metric("Zysk dzienny z BESS", f"{f['profit_battery_daily']:.2f} PLN")
        col_c.error(f"🔴 KOSZT ZWŁOKI (6 m-cy): {f['waiting_cost']:.2f} PLN")

        st.write("---")
        st.subheader("📥 Pobierz Twój Audyt PDF")
        st.markdown(
          "Udostępniamy to narzędzie w 100% za darmo, aby walczyć z dezinformacją na rynku OZE. "
          "**Nie sprzedajemy instalacji ani nie przekazujemy danych handlowcom.**\n\n"
          "Podaj e-mail, aby pobrać inżynieryjny PDF. Za kilka dni wyślemy Ci jedną wiadomość z pytaniem: "
          "*Czy ten raport pomógł Ci uchronić się przed zawyżoną ofertą?*"
        )

        contact_email = st.text_input("Twój e-mail:")
        if st.button("Generuj PDF i pomóż ulepszać system"):
            if "@" in contact_email and len(contact_email) > 5:
                chart_data = {
                    "hours": list(range(24)),
                    "pv_kw": f['pv_generation'].tolist(),
                    "cons_kw": f['consumption'].tolist(),
                    "prices": day_prices["price_pln_mwh"].tolist(),
                    "cheap_hours": day_prices["price_pln_mwh"].nsmallest(3).index.tolist(),
                    "expensive_hours": day_prices["price_pln_mwh"].nlargest(3).index.tolist()
                }
                
                output_pdf = f"data/audyt_{uuid.uuid4().hex[:8]}.pdf"
                generate_pdf_report(
                    output_path=output_pdf, client={"city": miasto, "annual_kwh": p['annual_kwh'], "battery_kwh": p['battery_kwh'], "profile": p['profile'], "pv_kwp": p['pv_kwp']},
                    date=target_date, cost_no_battery=f['cost_no_battery_daily'], cost_with_battery=f['cost_with_battery_daily'],
                    profit_daily=f['profit_battery_daily'], waiting_cost=f['waiting_cost'], chart_data=chart_data
                )
                
                with open(output_pdf, "rb") as file:
                    st.download_button("📥 Pobierz Audyt PDF", file, file_name="Audyt_ENTSOE.pdf", mime="application/pdf")
                
                # Zapis lokalny
                with open("data/beta_testers.csv", "a", encoding="utf-8") as file_csv:
                    file_csv.write(f"{miasto},{p['pv_kwp']},{p['battery_kwh']},{contact_email}\n")

                # WYSYŁKA DO TELEGRAM
                tg_msg_lead = f"⚡ NOWY LEAD!\nMiasto: {miasto}\nPV: {p['pv_kwp']} kWp\nBESS: {p['battery_kwh']} kWh\nEmail: {contact_email}"
                try:
                    requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", data={"chat_id": TG_CHAT_ID, "text": tg_msg_lead}, timeout=3)
                except Exception:
                    pass
                
                st.success("✅ Raport wygenerowany! Dziękujemy za pomoc w kalibracji.")
            else:
                st.error("Wprowadź poprawny adres e-mail.")
