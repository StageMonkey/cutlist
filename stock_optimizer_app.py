import streamlit as st
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import pandas as pd
import re
from fractions import Fraction
import io
from fpdf import FPDF

# --- Conversion utilities ---

def parse_length(length_str):
    length_str = length_str.strip().lower().replace('feet', "'").replace('foot', "'").replace('ft', "'").replace('inches', '"').replace('inch', '"').replace('in', '"')
    ft, inch = 0, 0
    match = re.match(r"(?:(\d+)')?\s*(\d+)?(?:\s*(\d+/\d+))?\s*(?:\"|in)?", length_str)
    if match:
        if match.group(1): ft = int(match.group(1))
        if match.group(2): inch += int(match.group(2))
        if match.group(3): inch += float(Fraction(match.group(3)))
    else:
        raise ValueError(f"Invalid format: '{length_str}'")
    return ft + inch / 12

def format_feet_inches(value, precision=32):
    total_inches = round(value * 12, 4)
    feet = int(total_inches // 12)
    inches = total_inches - feet * 12
    whole_inches = int(inches)
    frac = inches - whole_inches
    frac_rounded = Fraction(frac).limit_denominator(precision)

    if frac_rounded.numerator == frac_rounded.denominator:
        whole_inches += 1
        frac_rounded = Fraction(0, 1)

    if whole_inches >= 12:
        feet += 1
        whole_inches -= 12

    frac_str = f" {frac_rounded.numerator}/{frac_rounded.denominator}" if frac_rounded.numerator != 0 else ""
    inch_str = f"{whole_inches}{frac_str}\"" if (whole_inches or frac_str) else ""

    return f"{feet}' {inch_str}".strip()

# --- Optimization logic ---

def fit_cuts_to_stock(stock_length, kerf, cuts):
    cuts_with_kerf = [(cut + kerf, cut) for cut in cuts]
    cuts_with_kerf.sort(reverse=True)

    bins = []
    bin_usage = []

    for cut_with_k, original_cut in cuts_with_kerf:
        best_fit_index = -1
        min_space_left = float('inf')

        for i, used in enumerate(bin_usage):
            space_left = stock_length - used
            if cut_with_k <= space_left and space_left - cut_with_k < min_space_left:
                best_fit_index = i
                min_space_left = space_left - cut_with_k

        if best_fit_index == -1:
            bins.append([original_cut])
            bin_usage.append(cut_with_k)
        else:
            bins[best_fit_index].append(original_cut)
            bin_usage[best_fit_index] += cut_with_k

    wastes = [round(stock_length - usage, 4) for usage in bin_usage]
    used_lengths = [round(usage, 4) for usage in bin_usage]
    return bins, wastes, used_lengths

def plot_cutting_layout(cuts_to_stock, kerf, stock_length):
    fig, ax = plt.subplots(figsize=(10, len(cuts_to_stock)))
    y_height = 1

    for i, stock in enumerate(cuts_to_stock):
        x_pos = 0
        for cut in stock:
            rect = patches.Rectangle((x_pos, i * y_height), cut, 0.8, edgecolor='black', facecolor='skyblue')
            ax.add_patch(rect)
            ax.text(x_pos + cut / 2, i * y_height + 0.4, format_feet_inches(cut), ha='center', va='center', fontsize=8)
            x_pos += cut
            if x_pos + kerf <= stock_length:
                ax.add_patch(patches.Rectangle((x_pos, i * y_height), kerf, 0.8, edgecolor='red', facecolor='lightcoral', hatch='//'))
                x_pos += kerf
        if x_pos < stock_length:
            ax.add_patch(patches.Rectangle((x_pos, i * y_height), stock_length - x_pos, 0.8, edgecolor='gray', facecolor='lightgray'))
            ax.text(x_pos + (stock_length - x_pos) / 2, i * y_height + 0.4, "Waste", ha='center', va='center', fontsize=8, color='gray')

    ax.set_xlim(0, stock_length)
    ax.set_ylim(0, len(cuts_to_stock))
    ax.set_yticks([(i + 0.4) * y_height for i in range(len(cuts_to_stock))])
    ax.set_yticklabels([f"Stock {i + 1}" for i in range(len(cuts_to_stock))])
    ax.set_xlabel("Length (ft)")
    ax.set_title("Cutting Layout Diagram")
    plt.tight_layout()
    return fig

def export_pdf(project_name, stock_length, kerf, layout_fig, summary_df):
    buffer = io.BytesIO()
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)

    # Cover page
    pdf.add_page()
    pdf.set_font("Helvetica", size=16)
    pdf.cell(0, 10, f"Project: {project_name}", ln=True)
    pdf.set_font("Helvetica", size=12)
    pdf.cell(0, 10, f"Stock Length: {format_feet_inches(stock_length)}", ln=True)
    pdf.cell(0, 10, f"Kerf: {format_feet_inches(kerf)}", ln=True)
    pdf.cell(0, 10, f"Total Stock Pieces Used: {len(summary_df)}", ln=True)

    # Layout diagram
    pdf.add_page()
    canvas_buffer = io.BytesIO()
    layout_fig.savefig(canvas_buffer, format='png')
    canvas_buffer.seek(0)
    pdf.image(canvas_buffer, x=10, y=20, w=190)
    canvas_buffer.close()

    # Summary table
    pdf.add_page()
    pdf.set_font("Helvetica", size=10)
    col_widths = [30, 70, 30, 30, 30]
    headers = summary_df.columns.tolist()

    for header, width in zip(headers, col_widths):
        pdf.cell(width, 10, header, border=1)
    pdf.ln()

    for _, row in summary_df.iterrows():
        for value, width in zip(row, col_widths):
            pdf.cell(width, 10, str(value), border=1)
        pdf.ln()

    pdf.output(buffer)
    buffer.seek(0)
    return buffer

# --- Streamlit UI ---

st.title("📏 Stock Cut Optimizer (Feet + Inches)")

project_name = st.text_input("Project Name", value="My Project")
stock_length_input = st.text_input("Stock Length", value="12'")
kerf_input = st.text_input("Kerf", value='1/8"')
cuts_input = st.text_area("Enter Cuts (one per line)", value="4' 3\"\n2' 7 1/2\"\n5'\n8 3/4\"")

if st.button("Optimize"):
    try:
        stock_length = parse_length(stock_length_input)
        kerf = parse_length(kerf_input)

        cuts = []
        invalid_cuts = []
        for line in cuts_input.strip().splitlines():
            if not line.strip():
                continue
            try:
                length = parse_length(line.strip())
                if length > stock_length:
                    invalid_cuts.append((line.strip(), length))
                else:
                    cuts.append(length)
            except Exception as e:
                st.warning(f"Could not parse line: '{line.strip()}' ({e})")

        if invalid_cuts:
            st.warning(f"The following cuts were longer than the stock length ({format_feet_inches(stock_length)}) and were omitted:")
            for text, val in invalid_cuts:
                st.text(f"  - {text} ({format_feet_inches(val)})")

        result, waste, used = fit_cuts_to_stock(stock_length, kerf, cuts)

        st.success(f"Total stock pieces used: {len(result)}")
        df = pd.DataFrame({
            "Stock #": [f"Stock {i+1}" for i in range(len(result))],
            "Cuts": [", ".join(format_feet_inches(c) for c in r) for r in result],
            "Used Length": [format_feet_inches(u) for u in used],
            "Waste": [format_feet_inches(w) for w in waste],
            "Efficiency (%)": [round((u / stock_length) * 100, 2) for u in used]
        })
        st.dataframe(df)

        fig = plot_cutting_layout(result, kerf, stock_length)
        st.pyplot(fig)

        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button("Download CSV", csv, f"{project_name}_cut_plan.csv", "text/csv")

        pdf_buffer = export_pdf(project_name, stock_length, kerf, fig, df)
        st.download_button("Download PDF", pdf_buffer, f"{project_name}_cut_plan.pdf", "application/pdf")

    except Exception as e:
        st.error(f"Error: {e}")
