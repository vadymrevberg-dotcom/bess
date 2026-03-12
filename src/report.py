# src/report.py
import os
import urllib.request
import textwrap
import matplotlib.pyplot as plt
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

FONT_REGULAR = 'Roboto-Regular'
FONT_BOLD = 'Roboto-Bold'

def setup_fonts():
    if not os.path.exists('Roboto-Regular.ttf'):
        urllib.request.urlretrieve("https://github.com/googlefonts/roboto/raw/main/src/hinted/Roboto-Regular.ttf", "Roboto-Regular.ttf")
    if not os.path.exists('Roboto-Bold.ttf'):
        urllib.request.urlretrieve("https://github.com/googlefonts/roboto/raw/main/src/hinted/Roboto-Bold.ttf", "Roboto-Bold.ttf")
    
    pdfmetrics.registerFont(TTFont(FONT_REGULAR, 'Roboto-Regular.ttf'))
    pdfmetrics.registerFont(TTFont(FONT_BOLD, 'Roboto-Bold.ttf'))

try:
    setup_fonts()
except Exception as e:
    print(f"Błąd ładowania fontów: {e}")
    FONT_REGULAR = 'Helvetica'
    FONT_BOLD = 'Helvetica-Bold'

def generate_pdf_report(
    output_path: str,
    client: dict,
    date: str,
    cost_no_battery: float,
    cost_with_battery: float,
    profit_daily: float,
    waiting_cost: float,
    chart_data: dict,
    ai_roast: str = "Kalkulacja wykonana od zera. Brak parametrów z oferty instalatora do weryfikacji."
):
    c = canvas.Canvas(output_path, pagesize=A4)
    width, height = A4

    # ==========================================
    # STRONA 1: MATEMATYKA I WYKRESY ENTSO-E
    # ==========================================
    c.setFont(FONT_BOLD, 22)
    c.setFillColorRGB(0.1, 0.2, 0.5)
    c.drawString(2 * cm, height - 3 * cm, "RAPORT OPŁACALNOŚCI: FOTOWOLTAIKA + BESS")
    
    c.setFont(FONT_REGULAR, 10)
    c.setFillColorRGB(0.3, 0.3, 0.3)
    c.drawString(2 * cm, height - 3.7 * cm, f"Analiza oparta na taryfach dynamicznych RCE (CENY BRUTTO) | Data: {date}")

    c.setStrokeColorRGB(0.8, 0.8, 0.8)
    c.roundRect(2 * cm, height - 6.5 * cm, 17 * cm, 2.3 * cm, 0.2 * cm, stroke=1, fill=0)
    c.setFillColorRGB(0, 0, 0)
    c.setFont(FONT_BOLD, 11)
    c.drawString(2.5 * cm, height - 4.8 * cm, f"Klient: {client['city']} | Profil: {client['profile']}")
    c.setFont(FONT_REGULAR, 10)
    c.drawString(2.5 * cm, height - 5.5 * cm, f"Instalacja PV: {client['pv_kwp']} kWp | Roczne zużycie: {client['annual_kwh']} kWh")
    c.drawString(2.5 * cm, height - 6.1 * cm, f"Rekomendowany Magazyn Energii: {client['battery_kwh']} kWh")

    # Wykresy
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(6, 7.5), gridspec_kw={'height_ratios': [1, 1.8]})
    categories = ['Bez magazynu', 'Z magazynem']
    values = [cost_no_battery, cost_with_battery]
    bars = ax1.bar(categories, values, color=['#e74c3c', '#2ecc71'], width=0.4)
    ax1.set_ylabel('Koszt dzienny (PLN)', fontsize=9)
    ax1.set_title('Dzienny koszt zakupu energii z sieci', fontsize=10, fontweight='bold')
    for bar in bars:
        yval = bar.get_height()
        ax1.text(bar.get_x() + bar.get_width()/2, yval + (abs(yval)*0.05), f'{round(yval, 2)} PLN', ha='center', va='top', fontweight='bold', fontsize=9)

    hours = chart_data["hours"]
    ax2.bar(hours, chart_data["pv_kw"], color='#f1c40f', alpha=0.6, label='Generacja PV (kWh)')
    ax2.plot(hours, chart_data["cons_kw"], color='#2980b9', linewidth=2, label='Zużycie (kWh)')
    ax2.set_xlabel('Godzina', fontsize=9)
    ax2.set_ylabel('Energia (kWh)', fontsize=9)
    
    ax3 = ax2.twinx()
    ax3.plot(hours, chart_data["prices"], color='#8e44ad', linestyle='--', alpha=0.8, label='Cena RCE (PLN/MWh)')
    ax3.set_ylabel('Cena giełdowa (PLN/MWh)', fontsize=9)

    for h in chart_data["cheap_hours"]:
        ax2.axvspan(h-0.5, h+0.5, color='#2ecc71', alpha=0.15)
    for h in chart_data["expensive_hours"]:
        ax2.axvspan(h-0.5, h+0.5, color='#e74c3c', alpha=0.15)

    lines_1, labels_1 = ax2.get_legend_handles_labels()
    lines_2, labels_2 = ax3.get_legend_handles_labels()
    ax2.legend(lines_1 + lines_2, labels_1 + labels_2, loc='upper center', bbox_to_anchor=(0.5, -0.15), ncol=2, fontsize=8)
    ax2.set_title('Magazyn jako tarcza przed drogim prądem', fontsize=10, fontweight='bold')

    plt.tight_layout()
    plt.savefig("temp_chart.png", dpi=150, bbox_inches='
