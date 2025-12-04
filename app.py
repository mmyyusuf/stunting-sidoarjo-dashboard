import streamlit as st
import pandas as pd
import geopandas as gpd
import folium
from folium import Choropleth
from streamlit_folium import st_folium
import plotly.express as px
import plotly.graph_objects as go

# ==================== PAGE CONFIG ====================
st.set_page_config(
    page_title="Sistem Informasi Stunting Sidoarjo",
    page_icon="🗺️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==================== CUSTOM CSS ====================
st.markdown("""
<style>
    .main-header {
        font-size: 3rem;
        font-weight: bold;
        text-align: center;
        color: #1e40af;
        margin-bottom: 0.5rem;
    }
    .sub-header {
        font-size: 1.5rem;
        text-align: center;
        color: #6366f1;
        margin-bottom: 2rem;
    }
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1.5rem;
        border-radius: 1rem;
        color: white;
        text-align: center;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 2rem;
    }
    .stTabs [data-baseweb="tab"] {
        height: 3rem;
        font-size: 1.1rem;
        font-weight: 600;
    }
</style>
""", unsafe_allow_html=True)

# ==================== LOAD DATA ====================
@st.cache_data
def load_data():
    """Load CSV dan GeoJSON data"""
    try:
        # Load CSV
        df = pd.read_csv("data_stunting.csv")
        
        # Load GeoJSON
        gdf = gpd.read_file("kecamatan_sidoarjo.geojson")
        
        return df, gdf
    except FileNotFoundError as e:
        st.error(f"❌ File tidak ditemukan: {e}")
        st.info("💡 Pastikan file berikut ada di folder yang sama dengan app.py:\n- data_stunting.csv\n- kecamatan_sidoarjo.geojson")
        st.stop()
    except Exception as e:
        st.error(f"❌ Error loading data: {e}")
        st.stop()

# ==================== DATA PROCESSING ====================
@st.cache_data
def process_data(_df, _gdf):
    """Agregasi dan merge data"""
    
    # Bersihkan nama kecamatan
    _df["nama_kecamatan"] = _df["nama_kecamatan"].astype(str).str.strip()
    _gdf["WADMKC"] = _gdf["WADMKC"].astype(str).str.strip()
    
    # Normalisasi stunting ke 1/0
    _df["stunting_balita"] = _df["stunting_balita"].astype(str).str.strip().str.lower()
    _df["stunting_balita"] = _df["stunting_balita"].map({
        "ya": 1, "y": 1, "tidak": 0, "t": 0
    }).fillna(0).astype(float)
    
    # Dissolve kecamatan (gabung polygon per kecamatan)
    gdf_kec = _gdf.dissolve(by="WADMKC").reset_index()
    
    # Agregasi data stunting
    agg_data = _df.groupby("nama_kecamatan").agg({
        "stunting_balita": ["mean", "sum", "count"]
    }).reset_index()
    
    agg_data.columns = ["nama_kecamatan", "mean_stunting", "jumlah_stunting", "jumlah_balita"]
    agg_data = agg_data.rename(columns={"nama_kecamatan": "WADMKC"})
    
    # Merge dengan GeoJSON
    merged = gdf_kec.merge(agg_data, on="WADMKC", how="left")
    
    # Fill missing values
    merged["mean_stunting"] = merged["mean_stunting"].fillna(0)
    merged["jumlah_balita"] = merged["jumlah_balita"].fillna(0).astype(int)
    merged["jumlah_stunting"] = merged["jumlah_stunting"].fillna(0).astype(int)
    
    # Calculate percentage
    merged["mean_stunting_percent"] = (merged["mean_stunting"] * 100).round(2)
    
    # Categorize
    def categorize(percent):
        if percent == 0:
            return "Tidak Ada Data", "#94a3b8"
        elif percent < 20:
            return "Rendah", "#22c55e"
        elif percent < 30:
            return "Sedang", "#eab308"
        else:
            return "Tinggi", "#ef4444"
    
    merged[["category", "color"]] = merged["mean_stunting_percent"].apply(
        lambda x: pd.Series(categorize(x))
    )
    
    # Ranking (hanya untuk yang ada data)
    merged_with_data = merged[merged["mean_stunting_percent"] > 0].copy()
    merged_with_data = merged_with_data.sort_values("mean_stunting_percent", ascending=False)
    merged_with_data["rank"] = range(1, len(merged_with_data) + 1)
    
    # Merge rank back
    merged = merged.merge(
        merged_with_data[["WADMKC", "rank"]], 
        on="WADMKC", 
        how="left"
    )
    merged["rank"] = merged["rank"].fillna(0).astype(int)
    
    return merged

# ==================== VISUALIZATION FUNCTIONS ====================
def create_folium_map(merged_gdf):
    """Create interactive Folium map"""
    
    # Create base map
    m = folium.Map(
        location=[-7.45, 112.7],
        zoom_start=11,
        tiles="OpenStreetMap"
    )
    
    # Add choropleth
    Choropleth(
        geo_data=merged_gdf.__geo_interface__,
        data=merged_gdf,
        columns=["WADMKC", "mean_stunting"],
        key_on="feature.properties.WADMKC",
        fill_color="RdYlGn_r",
        nan_fill_color="#e2e8f0",
        fill_opacity=0.7,
        line_opacity=0.3,
        legend_name="Persentase Rata-rata Stunting (%)"
    ).add_to(m)
    
    # Popup template
    popup_template = """
    <div style="font-family: Arial; font-size:14px; line-height:1.8; padding:8px; min-width:220px;">
        <div style="font-weight:700; font-size:18px; margin-bottom:10px; color:#1e40af;">
            📍 {WADMKC}
        </div>
        <hr style="margin: 8px 0; border: none; border-top: 2px solid #e2e8f0;">
        <div><b>👶 Jumlah Balita:</b> {jumlah_balita}</div>
        <div><b>⚠️ Jumlah Stunting:</b> {jumlah_stunting}</div>
        <div><b>📊 Persentase:</b> <span style="color:{color}; font-weight:bold;">{mean_stunting_percent:.2f}%</span></div>
        <div><b>🏷️ Kategori:</b> <span style="color:{color}; font-weight:bold;">{category}</span></div>
        {rank_html}
    </div>
    """
    
    # Add interactive polygons
    for _, row in merged_gdf.iterrows():
        rank_html = f'<div><b>🏆 Ranking:</b> #{int(row["rank"])}</div>' if row["rank"] > 0 else ""
        
        html = popup_template.format(
            WADMKC=row["WADMKC"],
            jumlah_balita=int(row["jumlah_balita"]),
            jumlah_stunting=int(row["jumlah_stunting"]),
            mean_stunting_percent=row["mean_stunting_percent"],
            category=row["category"],
            color=row["color"],
            rank_html=rank_html
        )
        
        iframe = folium.IFrame(html, width=280, height=220)
        popup = folium.Popup(iframe, max_width=300)
        
        tooltip_text = f"{row['WADMKC']} — {row['mean_stunting_percent']:.2f}% ({int(row['jumlah_stunting'])}/{int(row['jumlah_balita'])})"
        
        folium.GeoJson(
            row["geometry"].__geo_interface__,
            style_function=lambda feat, c=row["color"]: {
                "fillOpacity": 0,
                "color": c,
                "weight": 2
            },
            popup=popup,
            tooltip=folium.Tooltip(tooltip_text)
        ).add_to(m)
    
    return m

def create_bar_chart(merged_gdf):
    """Create bar chart of stunting by kecamatan"""
    
    data_sorted = merged_gdf[merged_gdf["mean_stunting_percent"] > 0].sort_values(
        "mean_stunting_percent", ascending=True
    )
    
    fig = go.Figure()
    
    fig.add_trace(go.Bar(
        y=data_sorted["WADMKC"],
        x=data_sorted["mean_stunting_percent"],
        orientation='h',
        marker=dict(
            color=data_sorted["mean_stunting_percent"],
            colorscale='RdYlGn_r',
            showscale=True,
            colorbar=dict(title="Persentase (%)")
        ),
        text=data_sorted["mean_stunting_percent"].apply(lambda x: f"{x:.2f}%"),
        textposition='outside',
        hovertemplate='<b>%{y}</b><br>Persentase: %{x:.2f}%<extra></extra>'
    ))
    
    fig.update_layout(
        title="Persentase Stunting per Kecamatan",
        xaxis_title="Persentase Stunting (%)",
        yaxis_title="Kecamatan",
        height=500,
        margin=dict(l=20, r=20, t=40, b=20),
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)'
    )
    
    return fig

def create_pie_chart(merged_gdf):
    """Create pie chart of category distribution"""
    
    data_with_data = merged_gdf[merged_gdf["mean_stunting_percent"] > 0]
    category_counts = data_with_data["category"].value_counts()
    
    colors_map = {
        "Rendah": "#22c55e",
        "Sedang": "#eab308",
        "Tinggi": "#ef4444"
    }
    
    fig = go.Figure(data=[go.Pie(
        labels=category_counts.index,
        values=category_counts.values,
        marker=dict(colors=[colors_map.get(cat, "#94a3b8") for cat in category_counts.index]),
        hole=0.4,
        textinfo='label+percent',
        textfont_size=14,
        hovertemplate='<b>%{label}</b><br>Jumlah: %{value}<br>Persentase: %{percent}<extra></extra>'
    )])
    
    fig.update_layout(
        title="Distribusi Kategori Stunting",
        height=400,
        margin=dict(l=20, r=20, t=40, b=20),
        paper_bgcolor='rgba(0,0,0,0)'
    )
    
    return fig

# ==================== MAIN APP ====================
def main():
    # Header
    st.markdown('<div class="main-header">🗺️ Sistem Informasi Stunting</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Kabupaten Sidoarjo - Jawa Timur</div>', unsafe_allow_html=True)
    
    # Load data
    with st.spinner("⏳ Memuat data..."):
        df, gdf = load_data()
        merged_gdf = process_data(df, gdf)
    
    # Calculate statistics
    total_kecamatan = len(merged_gdf)
    kec_with_data = len(merged_gdf[merged_gdf["mean_stunting_percent"] > 0])
    total_balita = int(merged_gdf["jumlah_balita"].sum())
    total_stunting = int(merged_gdf["jumlah_stunting"].sum())
    avg_percent = (total_stunting / total_balita * 100) if total_balita > 0 else 0
    
    # Metrics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            label="📍 Total Kecamatan",
            value=f"{total_kecamatan}",
            delta=f"{kec_with_data} ada data"
        )
    
    with col2:
        st.metric(
            label="⚠️ Kasus Stunting",
            value=f"{total_stunting:,}",
            delta=f"{avg_percent:.2f}%"
        )
    
    with col3:
        st.metric(
            label="👶 Total Balita",
            value=f"{total_balita:,}"
        )
    
    with col4:
        kategori_tertinggi = merged_gdf[merged_gdf["mean_stunting_percent"] > 0]["category"].value_counts().idxmax()
        st.metric(
            label="🏷️ Kategori Dominan",
            value=kategori_tertinggi
        )
    
    st.markdown("---")
    
    # Tabs
    tab1, tab2, tab3 = st.tabs(["🗺️ Peta Interaktif", "📊 Analisis Data", "📋 Data Tabel"])
    
    with tab1:
        st.subheader("Peta Stunting Kabupaten Sidoarjo")
        
        col_map, col_legend = st.columns([3, 1])
        
        with col_map:
            folium_map = create_folium_map(merged_gdf)
            st_folium(folium_map, width=None, height=600)
        
        with col_legend:
            st.markdown("### 📊 Legend")
            st.markdown("""
            <div style="padding: 1rem; background: #f8fafc; border-radius: 0.5rem;">
                <div style="margin-bottom: 0.8rem;">
                    <span style="display: inline-block; width: 20px; height: 20px; background: #22c55e; border-radius: 4px; margin-right: 8px;"></span>
                    <b>Rendah</b> (&lt;20%)
                </div>
                <div style="margin-bottom: 0.8rem;">
                    <span style="display: inline-block; width: 20px; height: 20px; background: #eab308; border-radius: 4px; margin-right: 8px;"></span>
                    <b>Sedang</b> (20-30%)
                </div>
                <div style="margin-bottom: 0.8rem;">
                    <span style="display: inline-block; width: 20px; height: 20px; background: #ef4444; border-radius: 4px; margin-right: 8px;"></span>
                    <b>Tinggi</b> (&gt;30%)
                </div>
                <div>
                    <span style="display: inline-block; width: 20px; height: 20px; background: #94a3b8; border-radius: 4px; margin-right: 8px;"></span>
                    <b>Tidak Ada Data</b>
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            st.markdown("---")
            
            st.markdown("### 🏆 Top 5 Kecamatan")
            top_5 = merged_gdf[merged_gdf["mean_stunting_percent"] > 0].nlargest(5, "mean_stunting_percent")
            
            for idx, row in top_5.iterrows():
                st.markdown(f"""
                <div style="padding: 0.8rem; margin-bottom: 0.5rem; background: white; border-left: 4px solid {row['color']}; border-radius: 0.3rem; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
                    <div style="font-weight: 600; font-size: 1rem;">{row['WADMKC']}</div>
                    <div style="color: {row['color']}; font-size: 1.3rem; font-weight: bold;">{row['mean_stunting_percent']:.2f}%</div>
                    <div style="font-size: 0.85rem; color: #64748b;">{int(row['jumlah_stunting'])}/{int(row['jumlah_balita'])} balita</div>
                </div>
                """, unsafe_allow_html=True)
    
    with tab2:
        st.subheader("Analisis Data Stunting")
        
        col_chart1, col_chart2 = st.columns(2)
        
        with col_chart1:
            st.plotly_chart(create_bar_chart(merged_gdf), use_container_width=True)
        
        with col_chart2:
            st.plotly_chart(create_pie_chart(merged_gdf), use_container_width=True)
        
        st.markdown("---")
        
        # Additional statistics
        col_stat1, col_stat2 = st.columns(2)
        
        with col_stat1:
            st.markdown("#### 📈 Statistik Detail")
            stats_df = pd.DataFrame({
                "Metrik": [
                    "Kecamatan dengan Data",
                    "Kecamatan Tanpa Data",
                    "Persentase Tertinggi",
                    "Persentase Terendah",
                    "Rata-rata Persentase"
                ],
                "Nilai": [
                    f"{kec_with_data} dari {total_kecamatan}",
                    f"{total_kecamatan - kec_with_data}",
                    f"{merged_gdf[merged_gdf['mean_stunting_percent'] > 0]['mean_stunting_percent'].max():.2f}%",
                    f"{merged_gdf[merged_gdf['mean_stunting_percent'] > 0]['mean_stunting_percent'].min():.2f}%",
                    f"{avg_percent:.2f}%"
                ]
            })
            st.dataframe(stats_df, hide_index=True, use_container_width=True)
        
        with col_stat2:
            st.markdown("#### 🎯 Kecamatan Tanpa Data")
            no_data_kec = merged_gdf[merged_gdf["mean_stunting_percent"] == 0]["WADMKC"].tolist()
            if no_data_kec:
                for kec in no_data_kec:
                    st.markdown(f"- {kec}")
            else:
                st.success("✅ Semua kecamatan memiliki data!")
    
    with tab3:
        st.subheader("Data Lengkap per Kecamatan")
        
        # Prepare display data
        display_df = merged_gdf[["WADMKC", "jumlah_balita", "jumlah_stunting", "mean_stunting_percent", "category", "rank"]].copy()
        display_df.columns = ["Kecamatan", "Jumlah Balita", "Jumlah Stunting", "Persentase (%)", "Kategori", "Ranking"]
        display_df = display_df.sort_values("Persentase (%)", ascending=False).reset_index(drop=True)
        
        # Format display
        display_df["Jumlah Balita"] = display_df["Jumlah Balita"].astype(int)
        display_df["Jumlah Stunting"] = display_df["Jumlah Stunting"].astype(int)
        display_df["Ranking"] = display_df["Ranking"].astype(int)
        display_df["Ranking"] = display_df["Ranking"].apply(lambda x: f"#{x}" if x > 0 else "-")
        
        st.dataframe(
            display_df,
            hide_index=True,
            use_container_width=True,
            height=600
        )
        
        # Download button
        csv = display_df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Download Data CSV",
            data=csv,
            file_name="data_stunting_sidoarjo.csv",
            mime="text/csv"
        )
    
    # Footer
    st.markdown("---")
    st.markdown(
        "<div style='text-align: center; color: #64748b; padding: 1rem;'>"
        "© 2025 Sistem Informasi Stunting Kabupaten Sidoarjo | "
        "Data visualisasi untuk monitoring kesehatan balita"
        "</div>",
        unsafe_allow_html=True
    )

if __name__ == "__main__":

    main()
