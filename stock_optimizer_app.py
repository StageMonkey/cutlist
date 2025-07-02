import streamlit as st
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import pandas as pd
import re
from fractions import Fraction

# --- Conversion utilities ---

def parse_length(length_str):
    length_str = length_str.strip().lower()

    # Normalize input
    length_str = (
        length_str.replace("feet", "'")
        .replace("foot", "'")
        .replace("ft", "'")
        .replace("inches", '"')
        .replace("inch", '"')
        .replace("in", '"')
    )

    ft, inch = 0, 0.0

    # Case: fraction or decimal only (assume inches)
    if re.fullmatch(r"\d+\s*/\s*\d+", length_str) or re.fullmatch(r"\d*\.\d+", length_str):
        try:
            inch = float(Fraction(length_str))
            return inch / 12
        except:
            pass

    # General parsing: handles things like 1' 2 1/2", 3'4", etc.
    match = re.match(r"(?:(\d+)')?\s*(\d+)?(?:\s*(\d+/\d+))?\s*(?:\"|$)", length_str)
    if match:
        if match.group(1):  # feet
            ft = int(match.group(1))
        if match.group(2):  # inches
            inch += int(match.group(2))
        if match.group(3):  # fractional inches
            inch += float(Fraction(match.group(3)))
        return ft + inch / 12

    raise ValueError(f"Invalid length format: '{length_str}'")
    
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
    fig, ax = plt.subplots(figsize=(12, len(cuts_to_stock) * 1.2))
    y_height = 1

    for i, stock in enumerate(cuts_to_stock):
        x_pos = 0
        for cut in stock:
            rect = patches.Rectangle((x_pos, i * y_height), cut, 0.8, edgecolor='black', facecolor='skyblue')
            ax.add_patch(rect)
            ax.text(x_pos + cut / 2, i * y_height + 0.4, format_feet_inches(cut), ha='center', va='center', fontsize=8, weight='bold')
            x_pos += cut
            if x_pos + kerf <= stock_length:
                kerf_rect = patches.Rectangle((x_pos, i * y_height), kerf, 0.8, edgecolor='red', facecolor='lightcoral', hatch='//')
                ax.add_patch(kerf_rect)
                ax.text(x_pos + kerf / 2, i * y_height + 0.4, "Kerf", ha='center', va='center', fontsize=6, color='red')
                x_pos += kerf

        # Waste section
        if x_pos < stock_length:
            waste_len = stock_length - x_pos
            waste_rect = patches.Rectangle((x_pos, i * y_height), waste_len, 0.8, edgecolor='gray', facecolor='lightgray')
            ax.add_patch(waste_rect)
            ax.text(x_pos + waste_len / 2, i * y_height + 0.4, "Waste", ha='center', va='center', fontsize=8, color='gray')

        # Summary label
        ax.text(stock_length + 0.2, i * y_height + 0.4,
                f"Used: {format_feet_inches(x_pos)}\nWaste: {format_feet_inches(stock_length - x_pos)}",
                va='center', fontsize=8)

    # Draw inch ruler across bottom
    tick_height = 0.2
    for ft in range(int(stock_length) + 1):
        for inch in range(0, 12):
            pos = ft + inch / 12
            if pos > stock_length:
                break
            ax.plot([pos, pos], [-tick_height, 0], color='black', lw=0.5)
            if inch == 0:
                ax.text(pos, -0.4, f"{ft}'", ha='center', va='top', fontsize=7)

    ax.set_xlim(0, stock_length + 2)
    ax.set_ylim(-1, len(cuts_to_stock) * y_height)
    ax.set_yticks([(i + 0.4) * y_height for i in range(len(cuts_to_stock))])
    ax.set_yticklabels([f"Stock {i + 1}" for i in range(len(cuts_to_stock))])
    ax.set_xlabel("Length (ft)")
    ax.set_title("Cutting Layout Diagram")
    ax.axis("off")
    plt.tight_layout()
    return fig

# --- Streamlit UI ---

st.title("📏 Stock Cut Optimizer (Feet + Inches)")

project_name = st.text_input("Project Name")
stock_length_input = st.text_input("Stock Length", value="12'")
kerf_input = st.text_input("Kerf", value='1/8"')
cuts_input = st.text_area("Enter Cuts (one per line, use format 'Qty @ Length')", value="3 @ 4' 3\"\n2 @ 2' 7 1/2\"\n5 @ 5'\n1 @ 8 3/4\"")
uploaded_file = st.file_uploader("Upload Cuts CSV", type=["csv"])

if st.button("Optimize"):
    try:
        stock_length = parse_length(stock_length_input)
        kerf = parse_length(kerf_input)

cuts = []
invalid_cuts = []

if uploaded_file:
    # Load CSV as DataFrame
    cuts_df = pd.read_csv(uploaded_file)
    
    st.write("✅ **Imported Cuts from CSV:**")
    st.dataframe(cuts_df)
    
    for _, row in cuts_df.iterrows():
        qty = int(row["qty"])
        length_str = str(row["cut"]).strip()
        
        try:
            length = parse_length(length_str)
            
            if length > stock_length:
                invalid_cuts.append((length_str, length))
            else:
                cuts.extend([length] * qty)
        except Exception as e:
            st.warning(f"Could not parse cut: '{length_str}' ({e})")

else:
    # Fall back to manual text input
    for line in cuts_input.strip().splitlines():
        if not line.strip():
            continue
        qty = 1
        m = re.match(r"^(\\d+)\\s*[@~]\\s*(.+)$", line.strip())
        if m:
            qty = int(m.group(1))
            length_str = m.group(2).strip()
        else:
            length_str = line.strip()
        
        try:
            length = parse_length(length_str)
            if length > stock_length:
                invalid_cuts.append((length_str, length))
            else:
                cuts.extend([length] * qty)
        except Exception as e:
            st.warning(f"Could not parse line: '{line.strip()}' ({e})")

         if invalid_cuts:
            st.warning(f"The following cuts were longer than the stock length "f"({format_feet_inches(stock_length)}) and were omitted:")
            for text, val in invalid_cuts:
                st.text(f"  - {text} ({format_feet_inches(val)})")

        result, waste, used = fit_cuts_to_stock(stock_length, kerf, cuts)

        st.markdown(f"### Project: {project_name}")
        st.markdown(f"**Stock Length**: {format_feet_inches(stock_length)}")
        st.markdown(f"**Kerf**: {format_feet_inches(kerf)}")

        st.success(f"Total stock pieces used: {len(result)}")
        df = pd.DataFrame({
            "Stock #": [f"Stock {i+1}" for i in range(len(result))],
            "Cuts": [" | ".join(format_feet_inches(c) for c in r) for r in result],
            "Used Length": [format_feet_inches(u) for u in used],
            "Waste": [format_feet_inches(w) for w in waste],
            "Efficiency (%)": [round((u / stock_length) * 100, 2) for u in used]
        })
        st.dataframe(df)

        fig = plot_cutting_layout(result, kerf, stock_length)
        st.pyplot(fig)

        csv_header = f"Project: {project_name}\nStock Length: {format_feet_inches(stock_length)}\nKerf: {format_feet_inches(kerf)}\n\n"
        csv = csv_header + df.to_csv(index=False)
        st.download_button("Download CSV", csv.encode('utf-8'), "cut_plan.csv", "text/csv")

    except Exception as e:
        st.error(f"Error: {e}")
