"""
Dashboard Analisis Kebutuhan Keterampilan Pasar Kerja Indonesia (III.12)
========================================================================
Membaca basis data SQLite hasil notebook (`ner_jobposting.sqlite`) dan menyajikan
halaman analisis sesuai Tabel 3.4 proposal.

CARA MENJALANKAN
----------------
Lokal:
    pip install streamlit pandas plotly
    streamlit run app.py

Google Colab (karena Colab tak bisa buka port langsung, pakai tunnel):
    !pip install streamlit plotly pyngrok -q
    !streamlit run app.py &>/content/log.txt &
    from pyngrok import ngrok
    print(ngrok.connect(8501))     # buka URL yang tampil

Pastikan file DB (`outputs/ner_jobposting.sqlite`) ada, atau ubah DB_PATH di bawah.
"""
import re
import sqlite3
from itertools import combinations
from collections import Counter

import pandas as pd
import streamlit as st
import plotly.express as px

# ============================================================================
# KONFIGURASI
# ============================================================================
import os as _os
from glob import glob as _glob

def _cari_db():
    """Cari file DB di lokasi-lokasi yang wajar, supaya dashboard tidak langsung
    error saat dijalankan orang lain di komputer berbeda."""
    kandidat = ["outputs/ner_jobposting.sqlite", "ner_jobposting.sqlite",
                "../outputs/ner_jobposting.sqlite", "/content/outputs/ner_jobposting.sqlite"]
    for k in kandidat:
        if _os.path.exists(k):
            return k
    lain = sorted(_glob("**/*ner_jobposting*.sqlite", recursive=True))
    return lain[0] if lain else kandidat[0]

DB_PATH = _cari_db()
SKILL_LABELS = ("SKILL", "SOFT_SKILL", "TOOL", "PROGRAMMING_LANGUAGE")

# ----------------------------------------------------------------------------
# (v14) Taksonomi Escudero et al. (2025) -- KATEGORISASI UTAMA skill di
# seluruh dashboard, MENGGANTIKAN SKILL/TOOL/SOFT_SKILL/PROGRAMMING_LANGUAGE
# sebagai pengelompokan/pewarnaan primer. Label mentah tsb tetap disimpan di
# DB dan masih ditampilkan sebagai info tambahan (kolom "Jenis Entitas Asli"),
# tapi bukan lagi sumbu utama analisis.
# ----------------------------------------------------------------------------
ESCUDERO_BROAD = ["Cognitive Skills", "Socioemotional Skills", "Manual Skills"]

ESCUDERO_BROAD_COLORS = {
    "Cognitive Skills":      "#3B82F6",   # biru
    "Socioemotional Skills": "#F59E0B",   # oranye
    "Manual Skills":         "#10B981",   # hijau
}

# 14 subkategori (Tabel 1, Escudero et al. 2025) -- warna tetap per subkategori,
# dikelompokkan berdekatan (nuansa warna) dengan kategori luas induknya supaya
# masih terlihat "keluarganya" secara visual.
ESCUDERO_SUB_COLORS = {
    # -- Cognitive Skills (nuansa biru-ungu) --
    "Cognitive skills (narrow sense)":                     "#3B82F6",
    "Computer (general) skills":                            "#60A5FA",
    "Software (specific) skills and technical support":     "#2563EB",
    "Machine Learning and Artificial Intelligence":          "#1D4ED8",
    "Financial skills":                                      "#6366F1",
    "Writing skills":                                        "#818CF8",
    "Project management skills":                             "#4F46E5",
    # -- Socioemotional Skills (nuansa oranye-kuning) --
    "Character skills (conscientiousness, emotional stability and openness to experience)": "#F59E0B",
    "Social skills (including agreeableness and extraversion)": "#FBBF24",
    "People management skills":                              "#D97706",
    "Customer service skills":                                "#FCD34D",
    # -- Manual Skills (nuansa hijau) --
    "Finger-dexterity skills":                                "#10B981",
    "Hand-foot-eye coordination skills":                       "#34D399",
    "Physical skills":                                         "#059669",
}

# ----------------------------------------------------------------------------
# (v14) Klasifikasi Pekerjaan ke Jabatan KBJI 2014 (Bagian 8d notebook).
# "Tidak Terklasifikasi" = judul pekerjaan yang tidak match referensi manapun
# dengan confidence memadai -- ditampilkan apa adanya, bukan disembunyikan.
# ----------------------------------------------------------------------------
KBJI_ORDER = ["Manajer", "Profesional", "Teknisi dan Asisten Profesional",
             "Tenaga Tata Usaha", "Tenaga Usaha Jasa dan Tenaga Penjualan",
             "Pekerja Terampil Pertanian, Kehutanan dan Perikanan",
             "Pekerja Pengolahan, Kerajinan, dan Ybdi",
             "Operator dan Perakit Mesin", "Pekerja Kasar", "Tidak Terklasifikasi"]

KBJI_COLORS = {
    "Manajer":                                              "#6366F1",
    "Profesional":                                            "#3B82F6",
    "Teknisi dan Asisten Profesional":                         "#06B6D4",
    "Tenaga Tata Usaha":                                       "#10B981",
    "Tenaga Usaha Jasa dan Tenaga Penjualan":                  "#F59E0B",
    "Pekerja Terampil Pertanian, Kehutanan dan Perikanan":      "#84CC16",
    "Pekerja Pengolahan, Kerajinan, dan Ybdi":                  "#F97316",
    "Operator dan Perakit Mesin":                               "#EF4444",
    "Pekerja Kasar":                                            "#A855F7",
    "Tidak Terklasifikasi":                                     "#94A3B8",
}

# ----------------------------------------------------------------------------
# Nama tampilan untuk label/skill_type -- HANYA untuk ditampilkan, nilai asli
# di database TIDAK diubah (filter & JOIN lain tetap memakai nilai mentah).
# "TECHNICAL_SKILL" adalah nilai kolom skill_type, "SKILL" adalah nilai kolom
# label -- keduanya merujuk konsep yang sama sehingga dipetakan ke nama & warna
# tampilan yang SAMA agar konsisten di seluruh dashboard.
# ----------------------------------------------------------------------------
LABEL_DISPLAY_NAMES = {
    "SKILL": "Technical Skill",
    "TECHNICAL_SKILL": "Technical Skill",
}

DOMAIN_DISPLAY_NAMES = {
    "General": "Others",
}

# Warna TETAP per jenis skill -- dipakai lewat color_discrete_map= di semua
# grafik, sehingga "Technical Skill" SELALU biru di halaman mana pun, tidak
# berganti warna saat memilih pekerjaan/lokasi yang berbeda.
LABEL_COLOR_MAP = {
    "Technical Skill": "#3B82F6",       # biru
    "SOFT_SKILL": "#F59E0B",            # oranye
    "TOOL": "#10B981",                  # hijau
    "PROGRAMMING_LANGUAGE": "#EF4444",  # merah
}

# Warna TETAP untuk importance & proficiency (nilai kolom sudah diverifikasi
# terhadap basis data: importance = REQUIRED/PREFERRED/UNKNOWN,
# proficiency = ADVANCED/INTERMEDIATE/BASIC/UNKNOWN).
IMPORTANCE_COLORS = {"REQUIRED": "#EF4444", "PREFERRED": "#F59E0B", "UNKNOWN": "#94A3B8"}
PROFICIENCY_COLORS = {"ADVANCED": "#EF4444", "INTERMEDIATE": "#F59E0B",
                      "BASIC": "#10B981", "UNKNOWN": "#94A3B8"}
# transferability = HIGH/MEDIUM/LOW (bukan TRANSFERABLE/JOB_SPECIFIC seperti
# draft sebelumnya -- sudah dicek langsung terhadap basis data).
TRANSFER_COLORS = {"HIGH": "#10B981", "MEDIUM": "#F59E0B", "LOW": "#6366F1", "UNKNOWN": "#94A3B8"}

# Warna tunggal untuk grafik non-kategorikal (satu seri saja)
CLR_TOOLS = "#F97316"
CLR_EDU = "#8B5CF6"
CLR_DEGREE = "#06B6D4"

# ----------------------------------------------------------------------------
# Pola teks pengalaman kerja yang salah tertangkap sebagai EDUCATION_LEVEL
# oleh model NER (mis. "3TAHUN", "1-2 tahun"). Dibuang HANYA dari tampilan --
# tidak mengubah data di database. Pola: angka diikuti kata "tahun"/"thn".
# Tidak menyentuh S1/D3/SMA/SMK/dst karena nilai itu tidak pernah mengandung
# kata "tahun"/"thn".
# ----------------------------------------------------------------------------
EXPERIENCE_LEAK_RE = re.compile(r"\d+\s*-?\s*\d*\s*(tahun|thn)\b", re.IGNORECASE)


def drop_experience_leak(series):
    """Kembalikan mask boolean: True untuk baris yang BUKAN leak pengalaman kerja."""
    return ~series.astype(str).str.contains(EXPERIENCE_LEAK_RE, regex=True, na=False)


# ----------------------------------------------------------------------------
# Normalisasi jenjang pendidikan. SMA dan SMK dibedakan sesuai instruksi
# anotasi proposal; hanya digabung jika teks aslinya memang menyebut keduanya.
# ----------------------------------------------------------------------------
def norm_edu(t):
    x = t.lower().strip()
    if re.search(r"\bs[\s\-.]?3\b", x) or "doktor" in x or "phd" in x or "doctoral" in x:
        return "S3"
    if re.search(r"\bs[\s\-.]?2\b", x) or "magister" in x or "master" in x or "pascasarjana" in x:
        return "S2"
    if re.search(r"\bs[\s\-.]?1\b", x) or "sarjana" in x or "strata 1" in x or "bachelor" in x \
       or x.startswith("s1") or "s.pd" in x or "s.ked" in x:
        return "S1"
    if re.search(r"\bd[\s\-.]?4\b", x) or "diploma 4" in x or "div" in x:
        return "D4"
    if re.search(r"\bd[\s\-.]?3\b|\bdiii\b", x) or "diploma 3" in x or x == "diploma":
        return "D3"
    if re.search(r"\bd[\s\-.]?2\b", x):
        return "D2"
    if re.search(r"\bd[\s\-.]?1\b", x):
        return "D1"
    if "diploma" in x:
        return "Diploma"
    if "mahasiswa" in x or "semester" in x or "enrolled" in x or "recent graduate" in x:
        return "Mahasiswa"
    if "sma/k" in x or "smk/a" in x:
        return "SMA/SMK"
    has_sma = "sma" in x or "smu" in x or "slta" in x
    has_smk = "smk" in x or "stm" in x
    if has_sma and has_smk:
        return "SMA/SMK"
    if has_smk:
        return "SMK"
    if has_sma:
        return "SMA"
    if "sederajat" in x or "menengah atas" in x or "paket c" in x:
        return "SMA/SMK"
    if "smp" in x or "sltp" in x or "menengah pertama" in x:
        return "SMP"
    if x == "sd" or "sekolah dasar" in x:
        return "SD"
    return t.strip()


EDU_ORDER = ["SD", "SMP", "SMA", "SMK", "SMA/SMK", "Mahasiswa",
            "D1", "D2", "D3", "D4", "Diploma", "S1", "S2", "S3"]


def edu_sort_key(categories):
    """Urutkan kategori jenjang: yang dikenal ikut EDU_ORDER, sisanya di akhir."""
    known = [c for c in EDU_ORDER if c in categories]
    unknown = sorted(c for c in categories if c not in EDU_ORDER)
    return known + unknown


st.set_page_config(page_title="Skill Market Dashboard", layout="wide",
                   initial_sidebar_state="expanded")


@st.cache_resource
def get_conn(path, sidik=None):
    # 'sidik' membuat koneksi dibuat ulang saat berkas database berganti.
    return sqlite3.connect(path, check_same_thread=False)


def _sidik_db():
    """Sidik jari berkas database: (ukuran, waktu ubah).

    Nilai ini ikut menjadi bagian kunci cache. Tanpa ini, mengganti berkas
    .sqlite TIDAK membuat tampilan berubah, karena Streamlit menganggap
    query yang sama pasti berhasil yang sama -- inilah sebab perubahan
    database sempat tidak muncul di dashboard.
    """
    try:
        st_ = _os.stat(DB_PATH)
        return (st_.st_size, int(st_.st_mtime))
    except OSError:
        return (0, 0)


@st.cache_data
def _q_cached(sql, params, sidik):
    # 'sidik' tidak dipakai di dalam badan fungsi; keberadaannya semata-mata
    # untuk membatalkan cache ketika berkas database berganti.
    return pd.read_sql(sql, get_conn(DB_PATH, sidik), params=params)


def q(sql, params=()):
    return _q_cached(sql, params, _sidik_db())


def relabel(df, col="label"):
    """Ganti nilai label/skill_type mentah menjadi nama tampilan (SKILL/TECHNICAL_SKILL -> Technical Skill)."""
    df = df.copy()
    df[col] = df[col].map(lambda x: LABEL_DISPLAY_NAMES.get(x, x))
    return df


def relabel_domain(df, col="skill_domain"):
    """Ganti nilai domain mentah menjadi nama tampilan (General -> Others)."""
    df = df.copy()
    df[col] = df[col].map(lambda x: DOMAIN_DISPLAY_NAMES.get(x, x))
    return df


def paginate(df, key_prefix, default_per_page=25):
    """Kontrol pagination generik: pilih jumlah per halaman + nomor halaman.
    Mengembalikan (slice_df, info_text)."""
    total = len(df)
    per_page = st.selectbox("Tampilkan per halaman", [10, 25, 50, 100],
                            index=[10, 25, 50, 100].index(default_per_page),
                            key=f"{key_prefix}_perpage")
    n_pages = max(1, -(-total // per_page))  # ceil division
    page_num = st.number_input("Halaman", min_value=1, max_value=n_pages,
                               value=1, step=1, key=f"{key_prefix}_page")
    start = (page_num - 1) * per_page
    end = start + per_page
    info = f"Menampilkan {start + 1}-{min(end, total)} dari total {total} baris. (Halaman {page_num}/{n_pages})"
    return df.iloc[start:end].reset_index(drop=True), info


@st.cache_data
def get_qualitative_color_map(values, palette_name="Dark24"):
    """Bangun peta warna TETAP untuk sekumpulan nilai kategori (diurutkan
    alfabetis agar konsisten setiap kali dipanggil, dan dihitung dari SELURUH
    kategori yang mungkin muncul -- bukan dari subset yang sedang tampil --
    sehingga warnanya tidak berubah saat memilih pekerjaan/lokasi berbeda)."""
    palette = getattr(px.colors.qualitative, palette_name)
    values = sorted(set(v for v in values if v is not None))
    return {v: palette[i % len(palette)] for i, v in enumerate(values)}


# ------------------------------------------------------------------ sidebar
st.sidebar.title("🔎 Skill Market")
page = st.sidebar.radio("Halaman", [
    "Ringkasan",
    "Jumlah Lowongan per Pekerjaan",
    "Klasifikasi Jabatan (KBJI 2014)",
    "Skill per Pekerjaan",
    "Detail Kebutuhan per Pekerjaan",
    "Lokasi & Pekerjaan",
    "Skill per Lokasi",
    "Skill Teratas & Berkembang",
    "Taksonomi Keterampilan",
    "Jenjang Pendidikan & Bidang Studi",
    "Skill yang Sering Muncul Bersama",
    "Tren Permintaan Skill",
    "Gaji yang Ditawarkan",
    "Occupation-Specific Skills",
])

# (v14) Filter global UTAMA sekarang berdasarkan kategori luas Escudero
# et al. (2025) -- MENGGANTIKAN filter SKILL/TOOL/SOFT_SKILL/PROGRAMMING_LANGUAGE
# lama. Semua query "s.label IN {label_sql}" versi lama diganti
# "s.escudero_broad_category IN {broad_sql}" di seluruh halaman.
broad_filter = st.sidebar.multiselect(
    "Filter kategori skill (Escudero et al. 2025)", ESCUDERO_BROAD,
    default=ESCUDERO_BROAD)
broad_sql = "(" + ",".join(f"'{b}'" for b in broad_filter) + ")" if broad_filter \
            else "('" + "','".join(ESCUDERO_BROAD) + "')"
# alias tetap dipakai di beberapa fungsi cache lama (mis. cooccurrence())
label_sql = broad_sql

st.sidebar.caption("Sumber: NER IndoBERT + pengayaan atribut Layer 2 "
                   "+ Taksonomi Escudero et al. (2025) + KBJI 2014.")

# Peta warna TETAP untuk domain & jenis skill, dihitung SEKALI dari seluruh
# data (bukan dari subset yang sedang tampil), agar warnanya konsisten dan
# kontras di semua halaman.
_all_domains = [DOMAIN_DISPLAY_NAMES.get(d, d) for d in q("SELECT DISTINCT skill_domain FROM skills").skill_domain.tolist()]
_all_entity_labels_raw = q("SELECT DISTINCT label FROM entities").label.tolist()
_all_entity_labels_display = sorted(set(LABEL_DISPLAY_NAMES.get(l, l) for l in _all_entity_labels_raw))
DOMAIN_COLOR_MAP = get_qualitative_color_map(_all_domains, "Dark24")
ENTITY_LABEL_COLOR_MAP = get_qualitative_color_map(_all_entity_labels_display, "Dark24")

# Legenda warna di sidebar, supaya konsisten warna terlihat jelas dari awal.
st.sidebar.markdown("---")
st.sidebar.markdown("**🎨 Legenda Kategori Skill (Escudero)**")
for lbl, clr in ESCUDERO_BROAD_COLORS.items():
    st.sidebar.markdown(
        f'<span style="color:{clr}; font-size:1.2em;">●</span> {lbl}',
        unsafe_allow_html=True)
# ----------------------------------------------------------------------------
# (v15) Panel diagnostik sumber data.
# Dashboard mencari file DB secara otomatis, sehingga bisa saja mengambil
# salinan LAMA yang kebetulan tertinggal di folder kerja. Panel ini menampilkan
# file mana yang benar-benar sedang dibaca, kapan terakhir diubah, dan apakah
# koreksi manual pembimbing sudah ada di dalamnya.
# ----------------------------------------------------------------------------
st.sidebar.markdown("---")
with st.sidebar.expander("🗄️ Sumber data yang sedang dipakai", expanded=False):
    _abs = _os.path.abspath(DB_PATH)
    _kolom = q("SELECT * FROM jobs LIMIT 1").columns.tolist()
    _n_job = q("SELECT COUNT(*) n FROM jobs").n[0]
    _n_unc = q("""SELECT COUNT(*) n FROM jobs
                  WHERE kbji_golongan_pokok_nama='Tidak Terklasifikasi'""").n[0]
    st.caption(f"**Berkas:** `{_abs}`")
    if _os.path.exists(DB_PATH):
        from datetime import datetime as _dt
        _mt = _dt.fromtimestamp(_os.path.getmtime(DB_PATH)).strftime("%d %b %Y %H:%M")
        _mb = _os.path.getsize(DB_PATH) / 1024 / 1024
        st.caption(f"**Terakhir diubah:** {_mt}  ·  {_mb:.1f} MB")
    st.caption(f"**Lowongan:** {_n_job:,}  ·  **Tidak terklasifikasi:** {_n_unc:,}")

    if "kbji_source" in _kolom:
        _n_man = q("""SELECT COUNT(*) n FROM jobs
                      WHERE kbji_source IN ('manual_review','telaah_pembimbing')""").n[0]
        if _n_man:
            st.caption(f"**Dikoreksi/ditetapkan manual:** {_n_man:,} lowongan "
                      "(lihat `kbji_override.py` dan `kbji_telaah_pembimbing.py`)")
    if "kbji_ditangguhkan" in _kolom:
        _n_tg = q("SELECT COUNT(*) n FROM jobs WHERE COALESCE(kbji_ditangguhkan,0)=1").n[0]
        if _n_tg:
            st.caption(f"**Ditangguhkan:** {_n_tg:,} lowongan, disembunyikan dari halaman "
                      "Klasifikasi Jabatan karena tautan aslinya sudah mati")

    _lain = sorted(set(_glob("**/*ner_jobposting*.sqlite", recursive=True)))
    if len(_lain) > 1:
        st.caption("Berkas serupa lain yang ditemukan (TIDAK dipakai):")
        for _f in _lain:
            if _os.path.abspath(_f) != _abs:
                st.caption(f"· `{_os.path.abspath(_f)}`")

if "kbji_source" not in q("SELECT * FROM jobs LIMIT 1").columns.tolist():
    st.sidebar.error(
        "⚠️ Basis data ini BELUM memuat koreksi manual pembimbing. "
        "Jalankan `python kbji_override.py <berkas.sqlite>` lebih dulu, lalu pastikan "
        "dashboard membaca berkas hasilnya. Buka panel 'Sumber data yang sedang dipakai' "
        "di atas untuk melihat berkas mana yang sedang terbaca.")

if st.sidebar.button("🔄 Muat ulang data", use_container_width=True,
                     help="Kosongkan cache dan baca ulang berkas database."):
    st.cache_data.clear()
    st.cache_resource.clear()
    st.rerun()

st.sidebar.markdown("**🗂️ Legenda Jabatan KBJI**")
with st.sidebar.expander("Lihat semua warna jabatan"):
    for lbl, clr in KBJI_COLORS.items():
        st.markdown(
            f'<span style="color:{clr}; font-size:1.1em;">●</span> {lbl}',
            unsafe_allow_html=True)


# ================================================================== halaman
def page_overview():
    st.title("📊 Ringkasan Pasar Kerja")
    jobs = q("SELECT COUNT(*) n FROM jobs").n[0]
    n_skill = q(f"SELECT COUNT(DISTINCT name) n FROM skills WHERE escudero_broad_category IN {broad_sql}").n[0]
    n_ent = q("SELECT COUNT(*) n FROM entities").n[0]
    n_comp = q("SELECT COUNT(*) n FROM companies").n[0]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Lowongan", f"{jobs:,}")
    c2.metric("Skill unik", f"{n_skill:,}")
    c3.metric("Total entitas", f"{n_ent:,}")
    c4.metric("Perusahaan", f"{n_comp:,}")

    st.subheader("Distribusi Entitas per Label")
    ent_raw = q("SELECT job_id, label, text FROM entities")
    # (v13) Buang entitas EDUCATION_LEVEL yang sebenarnya salah label (isinya
    # teks pengalaman kerja seperti "3 tahun", "3TAHUN") dari hitungan ini.
    is_edu = ent_raw.label == "EDUCATION_LEVEL"
    ent_raw = ent_raw[~is_edu | (is_edu & drop_experience_leak(ent_raw.text))]
    ent_raw = relabel(ent_raw, "label")
    ent = ent_raw.groupby("label").size().reset_index(name="n").sort_values("n", ascending=False)
    st.plotly_chart(px.bar(ent, x="label", y="n", color="label",
                    color_discrete_map=ENTITY_LABEL_COLOR_MAP,
                    labels={"label": "Label", "n": "Jumlah"}),
                    use_container_width=True)

    # (v14) Kategori skill Escudero et al. (2025) -- kategorisasi UTAMA
    st.subheader("Kategori Skill (Taksonomi Escudero et al. 2025)")
    colE1, colE2 = st.columns(2)
    with colE1:
        st.markdown("**Kategori Luas**")
        broad = q("SELECT escudero_broad_category, COUNT(*) n FROM skills GROUP BY 1 ORDER BY 2 DESC")
        st.plotly_chart(px.pie(broad, names="escudero_broad_category", values="n", hole=.4,
                        color="escudero_broad_category", color_discrete_map=ESCUDERO_BROAD_COLORS),
                        use_container_width=True)
    with colE2:
        st.markdown("**14 Subkategori**")
        sub = q("SELECT escudero_subcategory, COUNT(*) n FROM skills GROUP BY 1 ORDER BY 2 DESC")
        st.plotly_chart(px.bar(sub.iloc[::-1], x="n", y="escudero_subcategory", orientation="h",
                        color="escudero_subcategory", color_discrete_map=ESCUDERO_SUB_COLORS,
                        labels={"n": "Jumlah", "escudero_subcategory": "Subkategori"},
                        height=420),
                        use_container_width=True)

    colA, colB = st.columns(2)
    with colA:
        st.subheader("Domain Skill (Layer 2)")
        dom = q("SELECT skill_domain, COUNT(*) n FROM skills GROUP BY skill_domain ORDER BY n DESC")
        dom = relabel_domain(dom, "skill_domain")
        st.plotly_chart(px.pie(dom, names="skill_domain", values="n", hole=.4,
                        color="skill_domain", color_discrete_map=DOMAIN_COLOR_MAP),
                        use_container_width=True)
    with colB:
        st.subheader("Jenis Skill")
        stype = q("SELECT skill_type, COUNT(*) n FROM skills GROUP BY skill_type ORDER BY n DESC")
        stype = relabel(stype, "skill_type")
        stype = stype.groupby("skill_type", as_index=False).n.sum()
        st.plotly_chart(px.pie(stype, names="skill_type", values="n", hole=.4,
                        color="skill_type", color_discrete_map=LABEL_COLOR_MAP),
                        use_container_width=True)


def page_top_skills():
    st.title("🔝 Skill Teratas & Berkembang")
    st.caption("Dikelompokkan berdasarkan taksonomi Escudero et al. (2025), bukan lagi "
              "SKILL/TOOL/SOFT_SKILL/PROGRAMMING_LANGUAGE.")
    topn = st.slider("Jumlah skill ditampilkan", 10, 50, 25)
    df = q(f"""SELECT s.name, s.label, s.escudero_broad_category, s.escudero_subcategory, COUNT(*) freq
              FROM job_skills js JOIN skills s ON s.id = js.skill_id
              WHERE s.escudero_broad_category IN {broad_sql}
              GROUP BY s.name, s.label ORDER BY freq DESC LIMIT {topn}""")
    st.plotly_chart(px.bar(df.iloc[::-1], x="freq", y="name", color="escudero_subcategory",
                    orientation="h", height=25 * topn + 120,
                    color_discrete_map=ESCUDERO_SUB_COLORS,
                    labels={"freq": "Jumlah Lowongan", "name": "Skill", "escudero_subcategory": "Subkategori"}),
                    use_container_width=True)
    st.dataframe(
        df.rename(columns={"name": "Skill", "label": "Jenis Entitas Asli",
                           "escudero_broad_category": "Kategori Luas",
                           "escudero_subcategory": "Subkategori", "freq": "Jumlah Lowongan"}),
        use_container_width=True, hide_index=True)


def page_job_title_summary():
    st.title("📋 Jumlah Lowongan per Pekerjaan")
    st.caption("Seluruh pekerjaan yang ada beserta jumlah lowongannya, diurutkan dari yang terbanyak.")
    df = q("""SELECT title, COUNT(*) n FROM jobs
              WHERE title != '' GROUP BY title ORDER BY n DESC""")
    cari = st.text_input("Cari nama pekerjaan (opsional)", "")
    if cari:
        df = df[df.title.str.contains(cari, case=False, na=False)]
    view, info = paginate(df, "jobtitle_summary")
    st.caption(info)
    view = view.rename(columns={"title": "Pekerjaan", "n": "Jumlah Lowongan"})
    view.index = view.index + 1
    st.dataframe(view, use_container_width=True)


def page_kbji_classification():
    st.title("🗂️ Klasifikasi Jabatan (KBJI 2014)")
    st.caption("Setiap judul pekerjaan dikelompokkan ke salah satu dari 9 jabatan "
              "KBJI 2014 (kode 1-9; TNI/POLRI dikecualikan). Metode: lexicon → fuzzy → k-NN "
              "embedding terhadap 2.155 nama pekerjaan riil dari dokumen KBJI. Lihat Bagian 8d "
              "pada notebook untuk detail metodologi.")

    # (v15) Lowongan yang ditangguhkan (mis. tautan sudah mati sehingga jabatannya
    # tidak dapat dipastikan) disembunyikan dari halaman ini atas keputusan
    # pembimbing. Barisnya TETAP ada di database agar total korpus utuh, dan tetap
    # ikut dihitung pada halaman lain yang menganalisis skill.
    _kolom_jobs = q("SELECT * FROM jobs LIMIT 1").columns.tolist()
    ADA_TANGGUH = "kbji_ditangguhkan" in _kolom_jobs
    FILTER = "WHERE COALESCE(kbji_ditangguhkan,0)=0" if ADA_TANGGUH else ""
    n_tangguh = q("SELECT COUNT(*) n FROM jobs WHERE COALESCE(kbji_ditangguhkan,0)=1").n[0] \
        if ADA_TANGGUH else 0

    dist = q(f"""SELECT kbji_golongan_pokok_nama AS jabatan, COUNT(*) n,
                        AVG(kbji_confidence) conf_rata
                 FROM jobs {FILTER} GROUP BY jabatan ORDER BY n DESC""")
    dist["jabatan"] = pd.Categorical(dist["jabatan"],
                                      categories=[g for g in KBJI_ORDER if g in dist.jabatan.values],
                                      ordered=True)
    dist = dist.sort_values("jabatan")

    c1, c2, c3 = st.columns(3)
    c1.metric("Total lowongan", f"{dist.n.sum():,}")
    n_unclass = int(dist.loc[dist.jabatan == "Tidak Terklasifikasi", "n"].sum()) \
        if "Tidak Terklasifikasi" in dist.jabatan.values else 0
    c2.metric("Tidak terklasifikasi", f"{n_unclass:,}",
             f"{n_unclass / dist.n.sum():.1%}" if dist.n.sum() else "0%")
    c3.metric("Rata-rata confidence", f"{(dist.n * dist.conf_rata).sum() / dist.n.sum():.2f}")

    st.subheader("Distribusi Lowongan per Jabatan")
    st.plotly_chart(px.bar(dist, x="jabatan", y="n", color="jabatan",
                    color_discrete_map=KBJI_COLORS,
                    labels={"jabatan": "Jabatan", "n": "Jumlah Lowongan"}),
                    use_container_width=True)

    _and = "AND COALESCE(kbji_ditangguhkan,0)=0" if ADA_TANGGUH else ""
    tab1, tab2 = st.tabs(["Jelajah per Jabatan", "Kualitas Klasifikasi (QA)"])

    with tab1:
        pilihan = [g for g in KBJI_ORDER if g in dist.jabatan.values]
        pick = st.selectbox("Pilih jabatan", pilihan)
        df = q(f"""SELECT title AS pekerjaan, COUNT(*) n, AVG(kbji_confidence) conf
                   FROM jobs WHERE kbji_golongan_pokok_nama = ? {_and}
                   GROUP BY title ORDER BY n DESC""", (pick,))
        view, info = paginate(df, "kbji_jelajah")
        st.caption(info)
        _top = view.head(20)
        _fig = px.bar(_top.iloc[::-1], x="n", y="pekerjaan", orientation="h",
                      height=30 * len(_top) + 150,
                      color_discrete_sequence=[KBJI_COLORS.get(pick, "#6366F1")],
                      labels={"n": "Jumlah Lowongan", "pekerjaan": "Pekerjaan"},
                      title=f"Pekerjaan teratas dalam jabatan '{pick}'")
        # Tanpa baris ini Plotly menyembunyikan sebagian nama pekerjaan ketika
        # batangnya rapat -- itulah sebab ada batang tanpa label pada tangkapan
        # layar Bu Tri.
        _fig.update_yaxes(tickmode="linear", dtick=1, automargin=True)
        _fig.update_xaxes(dtick=1)
        st.plotly_chart(_fig, use_container_width=True)
        st.dataframe(
            view.rename(columns={"pekerjaan": "Pekerjaan", "n": "Jumlah Lowongan", "conf": "Confidence Rata-rata"}),
            use_container_width=True, hide_index=True)

    with tab2:
        st.caption("Klasifikasi dengan confidence rendah lebih berisiko salah -- berguna untuk "
                  "spot-check manual atau menambah kata kunci lexicon di notebook.")
        low = q(f"""SELECT title AS pekerjaan, kbji_golongan_pokok_nama AS jabatan,
                           kbji_confidence AS conf
                    FROM jobs WHERE title != '' {_and} GROUP BY title
                    ORDER BY conf ASC LIMIT 100""")
        st.dataframe(
            low.rename(columns={"pekerjaan": "Pekerjaan", "jabatan": "Jabatan", "conf": "Confidence"}),
            use_container_width=True, hide_index=True)


def page_skill_by_job():
    st.title("💼 Skill per Pekerjaan")
    titles = q("""SELECT title, COUNT(*) n FROM jobs
                  WHERE title != '' GROUP BY title ORDER BY n DESC LIMIT 300""")
    pick = st.selectbox("Pilih pekerjaan", titles.title.tolist())
    df = q(f"""SELECT s.name, s.label, s.escudero_subcategory, COUNT(*) freq
              FROM jobs j JOIN job_skills js ON js.job_id = j.id
              JOIN skills s ON s.id = js.skill_id
              WHERE j.title = ? AND s.escudero_broad_category IN {broad_sql}
              GROUP BY s.name, s.label ORDER BY freq DESC LIMIT 25""", (pick,))
    if df.empty:
        st.info("Belum ada skill tercatat untuk pekerjaan ini.")
    else:
        st.plotly_chart(px.bar(df.iloc[::-1], x="freq", y="name", color="escudero_subcategory",
                        orientation="h", color_discrete_map=ESCUDERO_SUB_COLORS,
                        labels={"freq": "Jumlah Lowongan", "name": "Skill", "escudero_subcategory": "Subkategori"}),
                        use_container_width=True)


def page_job_detail():
    st.title("🧭 Detail Kebutuhan per Pekerjaan")
    st.caption("Untuk pekerjaan terpilih: skill lengkap dengan taksonomi Layer 2 "
              "(domain, transferability, importance, proficiency), tools, jenjang pendidikan, "
              "dan bidang studi yang diminta.")
    titles = q("""SELECT title, COUNT(*) n FROM jobs WHERE title != ''
                  GROUP BY title ORDER BY n DESC LIMIT 300""")
    pick = st.selectbox("Pilih pekerjaan", titles.title.tolist())
    n_job = int(titles.loc[titles.title == pick, "n"].iloc[0])
    st.markdown(f"### {pick} · {n_job} lowongan")

    # (v14) Jabatan KBJI 2014 untuk pekerjaan ini
    kbji_info = q("""SELECT kbji_golongan_pokok_nama, kbji_confidence FROM jobs
                     WHERE title = ? LIMIT 1""", (pick,))
    if not kbji_info.empty:
        gnama = kbji_info.kbji_golongan_pokok_nama.iloc[0]
        gconf = kbji_info.kbji_confidence.iloc[0]
        gclr = KBJI_COLORS.get(gnama, "#94A3B8")
        st.markdown(
            f'🗂️ Jabatan KBJI: <span style="background-color:{gclr}22; '
            f'color:{gclr}; padding:2px 10px; border-radius:12px; font-weight:600;">'
            f'{gnama}</span> &nbsp; <span style="color:#94A3B8;">(confidence {gconf:.2f})</span>',
            unsafe_allow_html=True)

    # ---- Tabel skill + taksonomi + importance/proficiency (agregat) ----
    st.subheader("🛠️ Skill yang Dibutuhkan + Taksonomi")
    skill_tax = q(f"""
        SELECT s.name AS skill, s.label, s.skill_domain AS domain,
               s.skill_function AS fungsi, s.transferability AS transfer,
               s.escudero_broad_category AS kategori_luas, s.escudero_subcategory AS subkategori,
               COUNT(*) AS frekuensi,
               SUM(CASE WHEN js.importance='REQUIRED'  THEN 1 ELSE 0 END) AS wajib,
               SUM(CASE WHEN js.importance='PREFERRED' THEN 1 ELSE 0 END) AS diutamakan,
               SUM(CASE WHEN js.proficiency='ADVANCED' THEN 1 ELSE 0 END) AS mahir
        FROM jobs j JOIN job_skills js ON js.job_id=j.id JOIN skills s ON s.id=js.skill_id
        WHERE j.title = ? AND s.escudero_broad_category IN {broad_sql}
        GROUP BY s.name, s.label ORDER BY frekuensi DESC LIMIT 40""", (pick,))
    if skill_tax.empty:
        st.info("Belum ada skill tercatat untuk pekerjaan ini.")
    else:
        st.plotly_chart(px.bar(skill_tax.head(20).iloc[::-1], x="frekuensi", y="skill",
                        color="subkategori", orientation="h", height=520,
                        hover_data=["label", "domain", "fungsi", "transfer", "wajib", "diutamakan"],
                        color_discrete_map=ESCUDERO_SUB_COLORS,
                        labels={"frekuensi": "Jumlah Lowongan", "skill": "Skill", "subkategori": "Subkategori Escudero"}),
                        use_container_width=True)
        st.markdown("**Tabel lengkap (taksonomi + importance/proficiency)**")
        st.dataframe(
            skill_tax.rename(columns={
                "skill": "Skill", "label": "Jenis Entitas Asli", "domain": "Domain (Layer 2)", "fungsi": "Fungsi",
                "transfer": "Transferability", "kategori_luas": "Kategori Luas (Escudero)",
                "subkategori": "Subkategori (Escudero)", "frekuensi": "Frekuensi",
                "wajib": "Wajib", "diutamakan": "Diutamakan", "mahir": "Mahir"}),
            use_container_width=True, hide_index=True)

    # ---- Ringkasan taksonomi pekerjaan ini ----
    st.subheader("🧬 Profil Taksonomi Pekerjaan Ini")
    c0, c1, c2, c3 = st.columns(4)
    with c0:
        esc = q(f"""SELECT s.escudero_broad_category AS kat, COUNT(*) n
                    FROM jobs j JOIN job_skills js ON js.job_id=j.id JOIN skills s ON s.id=js.skill_id
                    WHERE j.title=? AND s.escudero_broad_category IN {broad_sql}
                    GROUP BY kat ORDER BY n DESC""", (pick,))
        st.markdown("**Kategori Escudero**")
        if not esc.empty:
            st.plotly_chart(px.pie(esc, names="kat", values="n", hole=.4,
                            color="kat", color_discrete_map=ESCUDERO_BROAD_COLORS),
                            use_container_width=True)
        else:
            st.info("Tidak ada data.")
    with c1:
        dom = q(f"""SELECT s.skill_domain AS domain, COUNT(*) n
                    FROM jobs j JOIN job_skills js ON js.job_id=j.id JOIN skills s ON s.id=js.skill_id
                    WHERE j.title=? AND s.escudero_broad_category IN {broad_sql}
                    GROUP BY s.skill_domain ORDER BY n DESC""", (pick,))
        st.markdown("**Domain**")
        if not dom.empty:
            dom = relabel_domain(dom, "domain")
            st.plotly_chart(px.pie(dom, names="domain", values="n", hole=.4,
                            color="domain", color_discrete_map=DOMAIN_COLOR_MAP),
                            use_container_width=True)
        else:
            st.info("Tidak ada data.")
    with c2:
        tr = q(f"""SELECT s.transferability AS t, COUNT(*) n
                   FROM jobs j JOIN job_skills js ON js.job_id=j.id JOIN skills s ON s.id=js.skill_id
                   WHERE j.title=? AND s.escudero_broad_category IN {broad_sql}
                   GROUP BY s.transferability ORDER BY n DESC""", (pick,))
        st.markdown("**Transferability**")
        if not tr.empty:
            st.plotly_chart(px.pie(tr, names="t", values="n", hole=.4,
                            color="t", color_discrete_map=TRANSFER_COLORS),
                            use_container_width=True)
        else:
            st.info("Tidak ada data.")
    with c3:
        imp = q(f"""SELECT COALESCE(NULLIF(js.importance,''),'UNKNOWN') AS imp, COUNT(*) n
                    FROM jobs j JOIN job_skills js ON js.job_id=j.id JOIN skills s ON s.id=js.skill_id
                    WHERE j.title=? AND s.escudero_broad_category IN {broad_sql}
                    GROUP BY imp ORDER BY n DESC""", (pick,))
        st.markdown("**Importance**")
        if not imp.empty:
            st.plotly_chart(px.pie(imp, names="imp", values="n", hole=.4,
                            color="imp", color_discrete_map=IMPORTANCE_COLORS),
                            use_container_width=True)
        else:
            st.info("Tidak ada data.")

    # ---- Tools (dari tabel skills yang sudah dinormalisasi, BUKAN teks
    # entitas mentah -- konsisten dengan halaman lain yang memakai nama
    # kanonik, bukan varian ejaan mentah) ----
    st.subheader("💻 Tools / Software")
    tl = q(f"""SELECT s.name, COUNT(*) n FROM jobs j JOIN job_skills js ON js.job_id=j.id
              JOIN skills s ON s.id=js.skill_id
              WHERE j.title=? AND s.label='TOOL' GROUP BY s.name ORDER BY n DESC LIMIT 15""", (pick,))
    if tl.empty:
        st.info("Tidak ada tool spesifik tercatat.")
    else:
        st.plotly_chart(px.bar(tl.iloc[::-1], x="n", y="name", orientation="h",
                        color_discrete_sequence=[CLR_TOOLS],
                        labels={"n": "Jumlah Lowongan", "name": "Tool"}),
                        use_container_width=True)

    # ---- Pendidikan & Bidang Studi ----
    st.subheader("🎓 Pendidikan & Bidang Studi yang Diminta")
    c4, c5 = st.columns(2)
    with c4:
        st.markdown("**Jenjang Pendidikan**")
        edu = q("""SELECT e.text FROM jobs j JOIN entities e ON e.job_id=j.id
                   WHERE j.title=? AND e.label='EDUCATION_LEVEL'""", (pick,))
        edu = edu[drop_experience_leak(edu.text)]
        if edu.empty:
            st.info("Tidak dicantumkan.")
        else:
            edu = edu.copy()
            edu["jenjang"] = edu["text"].map(norm_edu)
            g = edu["jenjang"].value_counts()
            g = g.reindex(edu_sort_key(g.index)).dropna().reset_index()
            g.columns = ["jenjang", "n"]
            st.plotly_chart(px.bar(g, x="jenjang", y="n", color_discrete_sequence=[CLR_EDU],
                            labels={"jenjang": "Jenjang", "n": "Jumlah"}),
                            use_container_width=True)
    with c5:
        st.markdown("**Bidang Studi (Degree Field)**")
        deg = q("""SELECT LOWER(e.text) field, COUNT(*) n FROM jobs j JOIN entities e ON e.job_id=j.id
                   WHERE j.title=? AND e.label='DEGREE_FIELD'
                   GROUP BY LOWER(e.text) ORDER BY n DESC LIMIT 15""", (pick,))
        if deg.empty:
            st.info("Tidak dicantumkan.")
        else:
            st.plotly_chart(px.bar(deg.iloc[::-1], x="n", y="field", orientation="h",
                            color_discrete_sequence=[CLR_DEGREE],
                            labels={"n": "Jumlah", "field": "Bidang Studi"}),
                            use_container_width=True)


def page_location_job_title():
    st.title("📍🗂️ Lokasi & Pekerjaan")
    tab1, tab2 = st.tabs(["Pilih Lokasi", "Ringkasan Semua Lokasi"])

    with tab1:
        st.caption("Pilih satu lokasi untuk melihat semua pekerjaan yang ada di sana, "
                  "diurutkan dari jumlah lowongan terbanyak.")
        locs = q("""SELECT l.name, COUNT(*) n FROM jobs j JOIN locations l ON l.id=j.location_id
                    WHERE l.name != '' GROUP BY l.name ORDER BY n DESC LIMIT 300""")
        pick = st.selectbox("Pilih lokasi", locs.name.tolist(), key="locjob_pick")
        df = q("""SELECT j.title, COUNT(*) n FROM jobs j JOIN locations l ON l.id=j.location_id
                  WHERE l.name=? AND j.title!='' GROUP BY j.title ORDER BY n DESC""", (pick,))
        if df.empty:
            st.info("Belum ada data pekerjaan untuk lokasi ini.")
        else:
            st.metric(f"Total lowongan di '{pick}'", f"{df.n.sum():,}")
            view, info = paginate(df, "locjob_detail", default_per_page=25)
            st.caption(info)
            st.plotly_chart(
                px.bar(view.iloc[::-1], x="n", y="title", orientation="h",
                      height=25 * len(view) + 140,
                      labels={"n": "Jumlah Lowongan", "title": "Pekerjaan"},
                      title=f"Pekerjaan di '{pick}'"),
                use_container_width=True)
            st.dataframe(
                view.rename(columns={"title": "Pekerjaan", "n": "Jumlah Lowongan"}),
                use_container_width=True, hide_index=True)

    with tab2:
        st.caption("Satu baris per lokasi: total lowongan dan jumlah pekerjaan unik di sana. "
                  "Bisa diurutkan dari lowongan terbanyak ATAU variasi pekerjaan terbanyak.")
        ring = q("""SELECT l.name AS lokasi, COUNT(*) AS total_lowongan,
                          COUNT(DISTINCT j.title) AS jumlah_pekerjaan_unik
                   FROM jobs j JOIN locations l ON l.id = j.location_id
                   WHERE l.name != '' GROUP BY l.name""")
        urut = st.radio("Urutkan berdasarkan",
                        ["Total Lowongan Terbanyak", "Variasi Pekerjaan Terbanyak"],
                        horizontal=True, key="locjob_ringkasan_urut")
        kolom = "total_lowongan" if urut == "Total Lowongan Terbanyak" else "jumlah_pekerjaan_unik"
        ring = ring.sort_values(kolom, ascending=False)
        view, info = paginate(ring, "locjob_ringkasan")
        st.caption(info)
        st.dataframe(
            view.rename(columns={"lokasi": "Lokasi", "total_lowongan": "Total Lowongan",
                                 "jumlah_pekerjaan_unik": "Pekerjaan Unik"}),
            use_container_width=True, hide_index=True)


def page_skill_by_location():
    st.title("📍 Skill per Lokasi")
    locs = q("""SELECT l.name, COUNT(*) n FROM jobs j JOIN locations l ON l.id=j.location_id
                GROUP BY l.name ORDER BY n DESC LIMIT 100""")
    pick = st.selectbox("Pilih lokasi", locs.name.tolist())
    df = q(f"""SELECT s.name, s.label, s.escudero_subcategory, COUNT(*) freq
              FROM jobs j JOIN locations l ON l.id=j.location_id
              JOIN job_skills js ON js.job_id=j.id JOIN skills s ON s.id=js.skill_id
              WHERE l.name = ? AND s.escudero_broad_category IN {broad_sql}
              GROUP BY s.name, s.label ORDER BY freq DESC LIMIT 25""", (pick,))
    if df.empty:
        st.info("Belum ada data untuk lokasi ini.")
    else:
        st.plotly_chart(px.bar(df.iloc[::-1], x="freq", y="name", color="escudero_subcategory",
                        orientation="h", color_discrete_map=ESCUDERO_SUB_COLORS,
                        labels={"freq": "Jumlah Lowongan", "name": "Skill", "escudero_subcategory": "Subkategori"}),
                        use_container_width=True)


def page_taxonomy():
    st.title("🧬 Taksonomi Keterampilan (Escudero 2025 + Layer 2)")
    st.caption("Atribut hasil pengayaan otomatis: kategori Escudero (broad+sub), skill_type, domain, "
              "function, transferability, importance, dan proficiency. Dihitung dari kemunculan skill di lowongan.")

    # (v14) Distribusi taksonomi Escudero -- ditaruh paling atas karena ini
    # kategorisasi UTAMA sekarang.
    st.subheader("Taksonomi Escudero et al. (2025)")
    colX, colY = st.columns(2)
    with colX:
        st.markdown("**Kategori Luas**")
        b = q(f"""SELECT escudero_broad_category AS kategori, COUNT(*) n FROM skills
                 WHERE escudero_broad_category IN {broad_sql} GROUP BY kategori ORDER BY n DESC""")
        st.plotly_chart(px.pie(b, names="kategori", values="n", hole=.4,
                        color="kategori", color_discrete_map=ESCUDERO_BROAD_COLORS),
                        use_container_width=True)
    with colY:
        st.markdown("**14 Subkategori**")
        s_ = q(f"""SELECT escudero_subcategory AS kategori, COUNT(*) n FROM skills
                  WHERE escudero_broad_category IN {broad_sql} GROUP BY kategori ORDER BY n DESC""")
        st.plotly_chart(px.pie(s_, names="kategori", values="n", hole=.4,
                        color="kategori", color_discrete_map=ESCUDERO_SUB_COLORS),
                        use_container_width=True)

    st.subheader("Distribusi Atribut Layer 2 (tingkat skill unik)")
    cols = st.columns(2)
    facets_skill = [("skill_type", "Jenis Skill"), ("skill_domain", "Domain Skill"),
                    ("skill_function", "Fungsi Skill"), ("transferability", "Transferability")]
    for i, (col, judul) in enumerate(facets_skill):
        df = q(f"""SELECT COALESCE(NULLIF({col},''),'(kosong)') AS kategori, COUNT(*) n
                   FROM skills WHERE escudero_broad_category IN {broad_sql}
                   GROUP BY kategori ORDER BY n DESC""")
        with cols[i % 2]:
            st.markdown(f"**{judul}**")
            if df.empty or (len(df) == 1 and df.kategori.iloc[0] == "(kosong)"):
                st.info("Atribut ini belum terisi di DB. Pastikan enrichment Layer 2 dijalankan.")
                continue
            if col == "skill_type":
                df = relabel(df, "kategori")
                df = df.groupby("kategori", as_index=False).n.sum()
                st.plotly_chart(px.pie(df, names="kategori", values="n", hole=.4,
                                color="kategori", color_discrete_map=LABEL_COLOR_MAP),
                                use_container_width=True)
            elif col == "skill_domain":
                df = relabel_domain(df, "kategori")
                st.plotly_chart(px.pie(df, names="kategori", values="n", hole=.4,
                                color="kategori", color_discrete_map=DOMAIN_COLOR_MAP),
                                use_container_width=True)
            elif col == "transferability":
                st.plotly_chart(px.pie(df, names="kategori", values="n", hole=.4,
                                color="kategori", color_discrete_map=TRANSFER_COLORS),
                                use_container_width=True)
            else:
                cmap = get_qualitative_color_map(df.kategori.tolist(), "Dark24")
                st.plotly_chart(px.pie(df, names="kategori", values="n", hole=.4,
                                color="kategori", color_discrete_map=cmap),
                                use_container_width=True)

    st.subheader("Importance & Proficiency (tingkat kemunculan di lowongan)")
    cols2 = st.columns(2)
    for i, (col, judul, cmap) in enumerate([("importance", "Importance", IMPORTANCE_COLORS),
                                            ("proficiency", "Proficiency", PROFICIENCY_COLORS)]):
        df = q(f"""SELECT COALESCE(NULLIF(js.{col},''),'UNKNOWN') AS kategori, COUNT(*) n
                   FROM job_skills js JOIN skills s ON s.id = js.skill_id
                   WHERE s.escudero_broad_category IN {broad_sql} GROUP BY kategori ORDER BY n DESC""")
        with cols2[i]:
            st.markdown(f"**{judul}**")
            if df.empty:
                st.info("Belum ada data.")
            else:
                st.plotly_chart(px.bar(df, x="kategori", y="n", color="kategori",
                                color_discrete_map=cmap,
                                labels={"kategori": judul, "n": "Jumlah"}),
                                use_container_width=True)

    st.subheader("Jelajah Skill per Subkategori Escudero")
    subs = q("SELECT DISTINCT escudero_subcategory FROM skills WHERE escudero_subcategory IS NOT NULL ORDER BY 1")
    if not subs.empty:
        pick = st.selectbox("Pilih subkategori", subs.escudero_subcategory.tolist())
        df = q("""SELECT s.name, s.label, s.skill_domain, s.transferability, COUNT(*) freq
                 FROM job_skills js JOIN skills s ON s.id = js.skill_id
                 WHERE s.escudero_subcategory = ?
                 GROUP BY s.name ORDER BY freq DESC LIMIT 30""", (pick,))
        st.dataframe(
            df.rename(columns={"name": "Skill", "label": "Jenis Entitas Asli", "skill_domain": "Domain",
                               "transferability": "Transferability", "freq": "Frekuensi"}),
            use_container_width=True, hide_index=True)

    st.subheader("Peta Domain × Fungsi")
    hm = q(f"""SELECT skill_domain, skill_function, COUNT(*) n FROM skills
              WHERE escudero_broad_category IN {broad_sql} AND skill_domain IS NOT NULL AND skill_function IS NOT NULL
              GROUP BY skill_domain, skill_function""")
    if not hm.empty:
        hm = relabel_domain(hm, "skill_domain")
        pivot = hm.pivot_table(index="skill_domain", columns="skill_function", values="n", fill_value=0)
        st.plotly_chart(px.imshow(pivot, text_auto=True, aspect="auto",
                        color_continuous_scale="Blues", labels=dict(color="jumlah skill")),
                        use_container_width=True)

    st.subheader("Peta Kategori Escudero × Jabatan KBJI")
    st.caption("Kategori skill apa yang paling dibutuhkan di tiap jabatan.")
    hm2 = q(f"""SELECT j.kbji_golongan_pokok_nama AS jabatan, s.escudero_broad_category AS kategori, COUNT(*) n
               FROM jobs j JOIN job_skills js ON js.job_id=j.id JOIN skills s ON s.id=js.skill_id
               WHERE s.escudero_broad_category IN {broad_sql} AND j.kbji_golongan_pokok_nama IS NOT NULL
               GROUP BY jabatan, kategori""")
    if not hm2.empty:
        pivot2 = hm2.pivot_table(index="jabatan", columns="kategori", values="n", fill_value=0)
        pivot2 = pivot2.reindex([g for g in KBJI_ORDER if g in pivot2.index])
        st.plotly_chart(px.imshow(pivot2, text_auto=True, aspect="auto",
                        color_continuous_scale="Purples", labels=dict(color="jumlah skill")),
                        use_container_width=True)


def page_education():
    st.title("🎓 Jenjang Pendidikan & Bidang Studi")
    st.caption("Distribusi jenjang pendidikan dan bidang studi yang diminta di seluruh lowongan.")

    edu_raw = q("SELECT text FROM entities WHERE label='EDUCATION_LEVEL'")
    n_before = len(edu_raw)
    edu_raw = edu_raw[drop_experience_leak(edu_raw.text)]
    n_removed = n_before - len(edu_raw)
    if n_removed:
        st.caption(f"({n_removed} entitas dibuang dari tampilan karena sebenarnya teks "
                  f"pengalaman kerja, mis. \"3 tahun\", bukan jenjang pendidikan.)")

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Jenjang Pendidikan")
        if edu_raw.empty:
            st.info("Belum ada data.")
        else:
            edu_raw = edu_raw.copy()
            edu_raw["jenjang"] = edu_raw["text"].map(norm_edu)
            g = edu_raw["jenjang"].value_counts()
            g = g.reindex(edu_sort_key(g.index)).dropna().reset_index()
            g.columns = ["jenjang", "n"]
            st.plotly_chart(px.bar(g, x="jenjang", y="n", color_discrete_sequence=[CLR_EDU],
                            labels={"jenjang": "Jenjang", "n": "Jumlah"}),
                            use_container_width=True)
    with c2:
        st.subheader("Bidang Studi Terbanyak")
        deg = q("""SELECT LOWER(text) field, COUNT(*) n FROM entities WHERE label='DEGREE_FIELD'
                   GROUP BY LOWER(text) ORDER BY n DESC LIMIT 20""")
        if deg.empty:
            st.info("Belum ada data.")
        else:
            st.plotly_chart(px.bar(deg.iloc[::-1], x="n", y="field", orientation="h",
                            color_discrete_sequence=[CLR_DEGREE],
                            labels={"n": "Jumlah", "field": "Bidang Studi"}),
                            use_container_width=True)

    st.subheader("Bidang Studi yang Diminta per Jenjang")
    cross = q("""SELECT e1.text edu, e2.text field
                 FROM entities e1 JOIN entities e2 ON e1.job_id = e2.job_id
                 WHERE e1.label='EDUCATION_LEVEL' AND e2.label='DEGREE_FIELD'""")
    cross = cross[drop_experience_leak(cross.edu)]
    if cross.empty:
        st.info("Tidak ada lowongan yang mencantumkan keduanya sekaligus.")
    else:
        cross = cross.copy()
        cross["jenjang"] = cross["edu"].map(norm_edu)
        cross["field"] = cross["field"].str.lower()
        top_fields = cross["field"].value_counts().head(10).index
        sub = cross[cross["field"].isin(top_fields)]
        pivot = sub.groupby(["jenjang", "field"]).size().reset_index(name="n")
        field_cmap = get_qualitative_color_map(top_fields.tolist(), "Dark24")
        st.plotly_chart(px.bar(pivot, x="jenjang", y="n", color="field",
                        color_discrete_map=field_cmap,
                        category_orders={"jenjang": edu_sort_key(pivot.jenjang.unique())},
                        labels={"jenjang": "Jenjang", "n": "Jumlah", "field": "Bidang Studi"},
                        title="Kombinasi jenjang x bidang studi (top 10 bidang)"),
                        use_container_width=True)


@st.cache_data
def cooccurrence(broad_sql, min_count, _sidik=None):
    rows = q(f"""SELECT js.job_id, s.name FROM job_skills js
                 JOIN skills s ON s.id=js.skill_id WHERE s.escudero_broad_category IN {broad_sql}""")
    pair = Counter()
    for _, grp in rows.groupby("job_id"):
        for a, b in combinations(sorted(set(grp["name"])), 2):
            pair[(a, b)] += 1
    data = [(a, b, c) for (a, b), c in pair.items() if c >= min_count]
    return pd.DataFrame(sorted(data, key=lambda x: -x[2]),
                        columns=["skill_1", "skill_2", "co_occurrence"])


def page_cooccurrence():
    st.title("🔗 Skill yang Sering Muncul Bersama")
    st.caption("Pasangan skill yang sering muncul bersama dalam satu lowongan.")
    min_c = st.slider("Minimal kemunculan bersama", 2, 50, 10)
    df = cooccurrence(label_sql, min_c, _sidik_db()).head(40)
    if df.empty:
        st.info("Tidak ada pasangan yang memenuhi ambang. Turunkan nilainya.")
    else:
        df["pair"] = df.skill_1 + " + " + df.skill_2
        st.plotly_chart(px.bar(df.iloc[::-1], x="co_occurrence", y="pair", orientation="h",
                        height=25 * len(df) + 120,
                        labels={"co_occurrence": "Jumlah Kemunculan Bersama", "pair": "Pasangan Skill"}),
                        use_container_width=True)
        st.dataframe(
            df[["skill_1", "skill_2", "co_occurrence"]].rename(
                columns={"skill_1": "Skill 1", "skill_2": "Skill 2",
                        "co_occurrence": "Kemunculan Bersama"}),
            use_container_width=True, hide_index=True)


# ----------------------------------------------------------------------------
# (v15) Periode analisis tren.
# Sebaran tanggal posting sangat timpang: bulan-bulan sebelum 2025-05 hanya
# berisi < 20 lowongan (sisa scraping), dan bulan terakhir (2026-05) terpotong
# karena pengambilan data berhenti di tengah bulan. Kalau semuanya diplot,
# grafik garis akan menggambarkan pola PENGAMBILAN DATA, bukan pola permintaan
# pasar. Karena itu tren dibatasi ke periode dengan cakupan memadai.
# ----------------------------------------------------------------------------
TREN_BULAN_MIN = "2025-05"
TREN_BULAN_MAX = "2026-04"
TREN_MIN_LOWONGAN_PER_BULAN = 50


@st.cache_data
def bulan_valid(_sidik=None):
    """Bulan yang punya cukup lowongan untuk dianalisis trennya."""
    d = q("""SELECT substr(posted_date,1,7) bulan, COUNT(*) n FROM jobs
             WHERE posted_date NOT IN ('','None') GROUP BY bulan ORDER BY bulan""")
    d = d[(d.bulan >= TREN_BULAN_MIN) & (d.bulan <= TREN_BULAN_MAX)
          & (d.n >= TREN_MIN_LOWONGAN_PER_BULAN)]
    return d


def page_trends():
    st.title("📈 Tren Permintaan Skill")

    bv = bulan_valid(_sidik_db())
    if bv.empty:
        st.warning("Tidak ada bulan dengan cakupan data memadai.")
        return
    total_bulanan = dict(zip(bv.bulan, bv.n))
    bulan_list = bv.bulan.tolist()

    st.caption(
        f"Periode analisis: **{bulan_list[0]} s.d. {bulan_list[-1]}** "
        f"({len(bulan_list)} bulan, {bv.n.sum():,} lowongan). Bulan di luar rentang ini "
        f"dikeluarkan karena berisi kurang dari {TREN_MIN_LOWONGAN_PER_BULAN} lowongan, "
        "sehingga fluktuasinya mencerminkan pola pengambilan data, bukan permintaan pasar.")

    satuan = st.radio(
        "Satuan sumbu Y",
        ["Persentase lowongan bulan itu (disarankan)", "Jumlah lowongan (absolut)"],
        horizontal=True, key="tren_satuan")
    pakai_persen = satuan.startswith("Persentase")
    if pakai_persen:
        st.caption("Persentase = jumlah lowongan yang menyebut skill ÷ total lowongan pada "
                  "bulan yang sama. Ini menghilangkan efek jumlah lowongan yang berbeda "
                  "antar bulan, sehingga naik-turunnya benar-benar berarti perubahan "
                  "permintaan relatif.")

    ph_bulan = ",".join("?" * len(bulan_list))

    def siapkan(df, kolom_seri):
        """Tambahkan kolom nilai (absolut/persen) dan lengkapi bulan yang kosong dengan 0."""
        idx = pd.MultiIndex.from_product(
            [sorted(df[kolom_seri].unique()), bulan_list], names=[kolom_seri, "bulan"])
        df = (df.set_index([kolom_seri, "bulan"])["n"]
                .reindex(idx, fill_value=0).reset_index())
        df["total_bulan"] = df["bulan"].map(total_bulanan)
        df["nilai"] = df["n"] / df["total_bulan"] * 100 if pakai_persen else df["n"]
        return df

    y_label = "% Lowongan Bulan Itu" if pakai_persen else "Jumlah Lowongan"

    tab_agg, tab_skill = st.tabs([
        "Tren per Kategori Escudero (gabungan)", "Tren per Skill Individual"])

    # ---------------------------------------------------------------- (poin 4)
    with tab_agg:
        st.subheader("Gabungan Cognitive / Socioemotional / Manual Skills")
        st.caption("Setiap garis = TOTAL seluruh skill dalam kategori luas tersebut. "
                  "Satu lowongan dihitung sekali per kategori, sehingga garisnya bisa "
                  "dibaca sebagai 'berapa persen lowongan yang meminta minimal satu "
                  "skill dari kategori ini'.")

        level = st.radio("Tingkat agregasi",
                         ["3 Kategori Luas", "14 Subkategori"],
                         horizontal=True, key="tren_level")
        kolom = ("escudero_broad_category" if level.startswith("3")
                 else "escudero_subcategory")

        agg = q(f"""SELECT substr(j.posted_date,1,7) AS bulan,
                          s.{kolom} AS kategori,
                          COUNT(DISTINCT j.id) n
                   FROM jobs j JOIN job_skills js ON js.job_id=j.id
                   JOIN skills s ON s.id=js.skill_id
                   WHERE substr(j.posted_date,1,7) IN ({ph_bulan})
                     AND s.escudero_broad_category IN {broad_sql}
                   GROUP BY bulan, kategori""", tuple(bulan_list))

        if agg.empty:
            st.info("Tidak ada data pada periode ini.")
        else:
            agg = siapkan(agg, "kategori")
            cmap = (ESCUDERO_BROAD_COLORS if level.startswith("3")
                    else ESCUDERO_SUB_COLORS)
            fig = px.line(agg, x="bulan", y="nilai", color="kategori", markers=True,
                          color_discrete_map=cmap,
                          labels={"bulan": "Bulan", "nilai": y_label, "kategori": "Kategori"})
            fig.update_xaxes(tickmode="array", tickvals=bulan_list)
            st.plotly_chart(fig, use_container_width=True)

            st.markdown("**Ringkasan perubahan (awal vs akhir periode)**")
            awal, akhir = bulan_list[0], bulan_list[-1]
            piv = agg.pivot_table(index="kategori", columns="bulan", values="nilai")
            ring = pd.DataFrame({
                "Kategori": piv.index,
                f"{awal}": piv[awal].values,
                f"{akhir}": piv[akhir].values,
                "Perubahan": piv[akhir].values - piv[awal].values,
                "Rata-rata": piv[bulan_list].mean(axis=1).values,
            }).sort_values("Rata-rata", ascending=False)
            fmt = "{:.1f}%" if pakai_persen else "{:.0f}"
            st.dataframe(ring.style.format({c: fmt for c in ring.columns[1:]}),
                         use_container_width=True, hide_index=True)

    # ---------------------------------------------------------------- (poin 3)
    with tab_skill:
        st.subheader("Tren skill tertentu")
        st.caption("Sebelumnya hanya 30 skill teratas yang bisa dipilih. Sekarang SELURUH "
                  "skill tersedia — gunakan kotak pencarian untuk menemukannya.")

        min_f = st.slider(
            "Tampilkan skill dengan minimal ... kemunculan", 1, 200, 20,
            help="Skill yang hanya muncul beberapa kali menghasilkan garis tren yang "
                 "tidak stabil. Turunkan ke 1 bila ingin melihat semuanya.")

        freq = q(f"""SELECT s.name, COUNT(*) f FROM job_skills js
                     JOIN skills s ON s.id=js.skill_id
                     WHERE s.escudero_broad_category IN {broad_sql}
                     GROUP BY s.name HAVING f >= {min_f} ORDER BY f DESC""")
        if freq.empty:
            st.info("Tidak ada skill yang memenuhi ambang. Turunkan nilainya.")
            return

        st.caption(f"{len(freq):,} skill tersedia untuk dipilih "
                  f"(dari total {q('SELECT COUNT(DISTINCT name) n FROM skills').n[0]:,} skill unik).")

        opsi = [f"{n} ({f}×)" for n, f in zip(freq.name, freq.f)]
        peta = dict(zip(opsi, freq.name))
        pilih = st.multiselect("Cari & pilih skill", opsi, default=opsi[:5],
                               key="tren_skill_pick")
        picks = [peta[o] for o in pilih]
        if not picks:
            st.info("Pilih minimal satu skill.")
            return

        ph = ",".join("?" * len(picks))
        df = q(f"""SELECT substr(j.posted_date,1,7) AS bulan, s.name, COUNT(DISTINCT j.id) n
                   FROM jobs j JOIN job_skills js ON js.job_id=j.id
                   JOIN skills s ON s.id=js.skill_id
                   WHERE s.name IN ({ph}) AND substr(j.posted_date,1,7) IN ({ph_bulan})
                   GROUP BY bulan, s.name""", tuple(picks) + tuple(bulan_list))
        if df.empty:
            st.info("Skill terpilih tidak muncul pada periode analisis.")
            return

        df = siapkan(df, "name")
        fig = px.line(df, x="bulan", y="nilai", color="name", markers=True,
                      color_discrete_map=get_qualitative_color_map(picks, "Dark24"),
                      labels={"bulan": "Bulan", "nilai": y_label, "name": "Skill"})
        fig.update_xaxes(tickmode="array", tickvals=bulan_list)
        st.plotly_chart(fig, use_container_width=True)


def page_salary():
    import math

    st.title("💰 Gaji yang Ditawarkan")

    _kol = q("SELECT * FROM jobs LIMIT 1").columns.tolist()
    if "salary_min" not in _kol:
        st.error("Kolom gaji belum ada di basis data. Jalankan lebih dulu:\n\n"
                "`python salary_import.py outputs/ner_jobposting.sqlite "
                "ALL_batches_gold_annotations.json`")
        return

    cakup = q("""SELECT COUNT(*) total, SUM(salary_min IS NOT NULL) ada FROM jobs""")
    total, ada = int(cakup.total[0]), int(cakup.ada[0])

    c1, c2 = st.columns(2)
    c1.metric("Lowongan mencantumkan gaji", f"{ada:,}", f"{ada/total:.1%} dari korpus")
    c2.metric("Tanpa informasi gaji", f"{total-ada:,}", f"{(total-ada)/total:.1%}")

    pakai_max = st.radio(
        "Angka yang dianalisis", ["Batas bawah (salary_min)", "Titik tengah rentang"],
        horizontal=True, key="gaji_dasar",
        help="Titik tengah = rata-rata batas bawah dan batas atas; untuk lowongan "
             "yang hanya mencantumkan satu angka, batas bawah yang dipakai.")
    kolom_gaji = ("salary_min" if pakai_max.startswith("Batas bawah")
                  else "((salary_min + COALESCE(salary_max, salary_min)) / 2.0)")

    FILTER = "WHERE salary_min IS NOT NULL"

    def rp(x):
        return f"Rp{x:,.0f}".replace(",", ".")

    def label_singkat(v):
        """Rp4.500.000 -> '4,5jt'; Rp500.000 -> '500rb'.

        Plotly secara bawaan menulis 4.5M (million, gaya Inggris). Dalam bahasa
        Indonesia satuannya 'jt' untuk juta dan 'rb' untuk ribu, dengan koma
        sebagai pemisah desimal.
        """
        if v >= 1_000_000:
            teks = f"{v/1_000_000:.1f}".rstrip("0").rstrip(".")
            return teks.replace(".", ",") + "jt"
        if v >= 1_000:
            return f"{v/1_000:.0f}rb"
        return f"{v:.0f}"

    def sumbu_rupiah(fig, sumbu="x", vmaks=None):
        """Ganti penanda sumbu gaji menjadi format Indonesia."""
        vmaks = vmaks or 1
        langkah = 500_000 if vmaks <= 6_000_000 else (
            1_000_000 if vmaks <= 15_000_000 else 5_000_000)
        atas = math.ceil(vmaks / langkah) * langkah + langkah
        nilai = list(range(0, int(atas), langkah))
        opsi = dict(tickmode="array", tickvals=nilai,
                    ticktext=[label_singkat(v) for v in nilai],
                    # hoverformat mengatur angka pada kotak keterangan saat kursor
                    # diarahkan. Tanpa ini Plotly menulis '50M' (million), bukan
                    # angka penuh bergaya Indonesia.
                    hoverformat=",.0f")
        (fig.update_xaxes if sumbu == "x" else fig.update_yaxes)(**opsi)
        # separators=",." menetapkan koma sebagai pemisah desimal dan titik
        # sebagai pemisah ribuan, sesuai kaidah bahasa Indonesia. Berlaku untuk
        # seluruh angka pada gambar ini, termasuk tooltip.
        fig.update_layout(separators=",.")
        return fig

    tab1, tab2, tab3 = st.tabs(
        ["Sebaran Keseluruhan", "Gaji per Jabatan KBJI", "Gaji per Pekerjaan"])

    # ------------------------------------------------------------------ tab 1
    with tab1:
        d = q(f"SELECT {kolom_gaji} AS gaji FROM jobs {FILTER}")
        s = d.gaji
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Median", rp(s.median()))
        k2.metric("Rata-rata", rp(s.mean()))
        k3.metric("Persentil 25", rp(s.quantile(.25)))
        k4.metric("Persentil 75", rp(s.quantile(.75)))
        st.caption("Median lebih tepat dipakai sebagai ukuran pemusatan di sini "
                  "karena sebaran gaji menjulur ke kanan: sedikit lowongan bergaji "
                  "sangat tinggi menarik rata-rata ke atas.")

        batas_h = math.ceil(float(s.quantile(0.99)) / 1_000_000) * 1_000_000
        fig = px.histogram(d[d.gaji <= batas_h], x="gaji", nbins=60,
                           color_discrete_sequence=["#6366F1"],
                           labels={"gaji": "Gaji", "count": "Jumlah Lowongan"},
                           title="Sebaran gaji yang ditawarkan")
        fig.add_vline(x=s.median(), line_dash="dash", line_color="#DC2626",
                      annotation_text=f"Median {rp(s.median())}")
        sumbu_rupiah(fig, "x", batas_h)
        fig.update_xaxes(range=[0, batas_h], title_text="Gaji (Rp per bulan)")
        st.plotly_chart(fig, use_container_width=True)
        n_luar = int((s > batas_h).sum())
        if n_luar:
            st.caption(f"Sumbu dipangkas pada {rp(batas_h)} (persentil 99); "
                      f"{n_luar} lowongan bergaji di atas itu tidak tergambar, "
                      "tetapi tetap ikut dalam perhitungan seluruh statistik di atas.")

        st.subheader("Menurut jenjang pendidikan yang diminta")
        edu = q(f"""SELECT e.text AS jenjang, {kolom_gaji} AS gaji FROM jobs j
                    JOIN entities e ON e.job_id=j.id AND e.label='EDUCATION_LEVEL'
                    WHERE j.salary_min IS NOT NULL""")
        if not edu.empty:
            g = (edu.groupby("jenjang")["gaji"]
                 .agg(["median", "count"]).reset_index()
                 .query("count >= 30").sort_values("median", ascending=False).head(12))
            if not g.empty:
                fig = px.bar(g.iloc[::-1], x="median", y="jenjang", orientation="h",
                             height=32 * len(g) + 150,
                             color_discrete_sequence=["#10B981"],
                             labels={"median": "Median Gaji (Rp)", "jenjang": "Jenjang"},
                             hover_data={"count": True})
                fig.update_yaxes(tickmode="linear", dtick=1, automargin=True)
                sumbu_rupiah(fig, "x", g["median"].max())
                st.plotly_chart(fig, use_container_width=True)
                st.caption("Hanya jenjang dengan minimal 30 lowongan yang ditampilkan. "
                          "Teks jenjang diambil apa adanya dari entitas EDUCATION_LEVEL "
                          "hasil model, sehingga satu jenjang bisa muncul dalam beberapa "
                          "penulisan berbeda.")

    # ------------------------------------------------------------------ tab 2
    with tab2:
        d = q(f"""SELECT kbji_golongan_pokok_nama AS jabatan, {kolom_gaji} AS gaji
                  FROM jobs {FILTER} AND COALESCE(kbji_ditangguhkan,0)=0""")
        g = (d.groupby("jabatan")["gaji"].agg(["median", "mean", "count"])
             .reset_index().query("count >= 10").sort_values("median", ascending=False))
        if g.empty:
            st.info("Belum ada jabatan dengan jumlah lowongan memadai.")
        else:
            fig = px.bar(g.iloc[::-1], x="median", y="jabatan", orientation="h",
                         height=42 * len(g) + 150, color="jabatan",
                         color_discrete_map=KBJI_COLORS,
                         labels={"median": "Median Gaji (Rp per bulan)",
                                 "jabatan": "Jabatan"},
                         title="Median gaji menurut jabatan KBJI")
            fig.update_yaxes(tickmode="linear", dtick=1, automargin=True)
            fig.update_layout(showlegend=False)
            sumbu_rupiah(fig, "x", g["median"].max())
            st.plotly_chart(fig, use_container_width=True)

            box = d[d.jabatan.isin(g.jabatan)]
            # Sumbu dipangkas di persentil 99. Tanpa ini, dua lowongan bergaji
            # Rp45-50 juta merentangkan sumbu sampai 50jt dan menjepit 99,95%
            # data ke seperlima kiri grafik sehingga kotaknya tak terbaca.
            batas = max(1_000_000, float(box.gaji.quantile(0.99)))
            batas = math.ceil(batas / 1_000_000) * 1_000_000
            di_luar = int((box.gaji > batas).sum())
            # Urutan kategori disamakan dengan grafik batang di atas (median menaik).
            urut = g.sort_values("median").jabatan.tolist()
            fig2 = px.box(box, x="gaji", y="jabatan", color="jabatan",
                          color_discrete_map=KBJI_COLORS, height=46 * len(g) + 200,
                          category_orders={"jabatan": urut},
                          labels={"gaji": "Gaji", "jabatan": "Jabatan"},
                          title="Sebaran gaji dalam tiap jabatan")
            fig2.update_yaxes(tickmode="linear", dtick=1, automargin=True)
            fig2.update_layout(showlegend=False, margin=dict(t=70))
            sumbu_rupiah(fig2, "x", batas)
            fig2.update_xaxes(range=[0, batas], title_text="Gaji (Rp per bulan)")
            st.plotly_chart(fig2, use_container_width=True)
            ket = ("Diagram kotak memperlihatkan bahwa rentang gaji DI DALAM satu "
                  "jabatan sering lebih lebar daripada selisih ANTAR jabatan.")
            if di_luar:
                ket += (f" Sumbu dipangkas pada {rp(batas)} (persentil 99); "
                       f"{di_luar} lowongan bergaji di atas itu tidak tergambar, "
                       "tetapi tetap ikut dalam perhitungan median dan kuartil.")
            st.caption(ket)

            tampil = g.copy()
            tampil["median"] = tampil["median"].map(rp)
            tampil["mean"] = tampil["mean"].map(rp)
            st.dataframe(tampil.rename(columns={
                "jabatan": "Jabatan", "median": "Median", "mean": "Rata-rata",
                "count": "Jumlah Lowongan"}), use_container_width=True, hide_index=True)
            st.caption("Hanya jabatan dengan minimal 10 lowongan bergaji yang ditampilkan.")

    # ------------------------------------------------------------------ tab 3
    with tab3:
        min_n = st.slider("Jumlah lowongan minimal per pekerjaan", 3, 50, 10,
                          help="Median dari sedikit lowongan sangat tidak stabil. "
                               "Turunkan bila ingin melihat pekerjaan yang jarang muncul.")
        d = q(f"""SELECT title AS pekerjaan, {kolom_gaji} AS gaji
                  FROM jobs {FILTER} AND title != ''""")
        g = (d.groupby("pekerjaan")["gaji"]
             .agg(median="median", count="count", p25=lambda x: x.quantile(.25),
                  p75=lambda x: x.quantile(.75))
             .reset_index().query("count >= @min_n"))
        if g.empty:
            st.info("Tidak ada pekerjaan yang memenuhi ambang. Turunkan nilainya.")
            return

        st.caption(f"{len(g):,} pekerjaan memenuhi ambang minimal {min_n} lowongan, "
                  f"mencakup {int(g['count'].sum()):,} lowongan bergaji.")

        atas = g.nlargest(15, "median")
        bawah = g.nsmallest(15, "median")
        for judul, sub, warna in [
                ("15 pekerjaan dengan median gaji tertinggi", atas, "#059669"),
                ("15 pekerjaan dengan median gaji terendah", bawah, "#DC2626")]:
            fig = px.bar(sub.sort_values("median"), x="median", y="pekerjaan",
                         orientation="h", height=30 * len(sub) + 150,
                         color_discrete_sequence=[warna],
                         hover_data={"count": True, "p25": ":,.0f", "p75": ":,.0f"},
                         labels={"median": "Median Gaji (Rp per bulan)",
                                 "pekerjaan": "Pekerjaan", "count": "Jumlah lowongan"},
                         title=judul)
            fig.update_yaxes(tickmode="linear", dtick=1, automargin=True)
            sumbu_rupiah(fig, "x", sub["median"].max())
            st.plotly_chart(fig, use_container_width=True)

        st.subheader("Bandingkan sebaran gaji antar pekerjaan")
        opsi = g.sort_values("count", ascending=False).pekerjaan.tolist()
        pilih = st.multiselect("Pilih pekerjaan (bisa lebih dari satu)", opsi,
                               default=opsi[:6], key="gaji_banding")
        if pilih:
            box = d[d.pekerjaan.isin(pilih)]
            batas = max(1_000_000, float(box.gaji.quantile(0.99)))
            batas = math.ceil(batas / 1_000_000) * 1_000_000
            di_luar = int((box.gaji > batas).sum())
            urut = (box.groupby("pekerjaan").gaji.median()
                    .sort_values().index.tolist())
            fig = px.box(box, x="gaji", y="pekerjaan",
                         color="pekerjaan",
                         color_discrete_map=get_qualitative_color_map(pilih, "Dark24"),
                         height=46 * len(pilih) + 200,
                         category_orders={"pekerjaan": urut},
                         labels={"gaji": "Gaji", "pekerjaan": "Pekerjaan"})
            fig.update_yaxes(tickmode="linear", dtick=1, automargin=True)
            fig.update_layout(showlegend=False, margin=dict(t=40))
            sumbu_rupiah(fig, "x", batas)
            fig.update_xaxes(range=[0, batas], title_text="Gaji (Rp per bulan)")
            st.plotly_chart(fig, use_container_width=True)
            st.caption("Diagram kotak memperlihatkan rentang gaji di dalam satu "
                      "pekerjaan, bukan hanya nilai tengahnya. Kotak yang lebar berarti "
                      "tawaran antar perusahaan untuk pekerjaan yang sama sangat beragam.")

        st.subheader("Tabel lengkap")
        cari = st.text_input("Cari pekerjaan tertentu", key="gaji_cari")
        tab = g.sort_values("median", ascending=False)
        if cari:
            tab = tab[tab.pekerjaan.str.contains(cari, case=False, na=False)]
        if tab.empty:
            st.info(f"Tidak ada pekerjaan yang cocok dengan '{cari}'.")
        else:
            tampil = tab.copy()
            for kol in ("median", "p25", "p75"):
                tampil[kol] = tampil[kol].map(rp)
            st.dataframe(tampil[["pekerjaan", "median", "p25", "p75", "count"]].rename(
                columns={"pekerjaan": "Pekerjaan", "median": "Median Gaji",
                         "p25": "Persentil 25", "p75": "Persentil 75",
                         "count": "Jumlah Lowongan"}),
                use_container_width=True, hide_index=True)
            st.caption("Persentil 25 dan 75 menunjukkan rentang tawaran yang lazim: "
                      "separuh lowongan untuk pekerjaan tersebut berada di antara "
                      "kedua angka itu.")


def page_skill_gap():
    st.title("🎯 Occupation-Specific Skills")
    st.caption("Membandingkan seberapa besar porsi suatu skill di SATU pekerjaan "
              "dibandingkan porsinya di SELURUH pasar kerja.")

    with st.expander("📖 Cara membaca halaman ini (klik untuk membuka)", expanded=True):
        st.markdown("""
**Apa yang dihitung.** Untuk setiap skill dilakukan perbandingan dua proporsi:

| Kolom | Rumus | Artinya |
|---|---|---|
| **Pangsa di Pekerjaan** | jumlah penyebutan skill di pekerjaan ini ÷ total penyebutan semua skill di pekerjaan ini | Dari 100 skill yang diminta lowongan pekerjaan ini, berapa yang berupa skill tersebut |
| **Pangsa di Pasar** | jumlah penyebutan skill di seluruh lowongan ÷ total penyebutan semua skill di seluruh lowongan | Angka pembanding (*baseline*): seberapa umum skill itu di pasar kerja secara keseluruhan |
| **Selisih** | Pangsa di Pekerjaan − Pangsa di Pasar | Seberapa **khas** skill itu bagi pekerjaan tersebut |

**Contoh angka.** Misalkan untuk pekerjaan *Data Analyst*: `microsoft excel` punya
Pangsa di Pekerjaan 0,082 (8,2%), Pangsa di Pasar 0,017 (1,7%), Selisih +0,065.
Dibacanya: *Excel menyusun 8,2% dari seluruh permintaan skill pada lowongan Data
Analyst, sementara di pasar kerja secara umum hanya 1,7%. Jadi Excel 4,8 kali
lebih menonjol pada pekerjaan ini daripada rata-rata pasar.*

**Cara membaca tandanya.**
- **Selisih positif besar** → skill pembeda (*distinctive*). Inilah yang membuat
  pekerjaan tersebut berbeda dari pekerjaan lain, dan yang paling relevan untuk
  rekomendasi kurikulum atau pelatihan yang spesifik.
- **Selisih mendekati nol** → skill generik. Diminta pekerjaan ini, tapi sama
  seringnya diminta pekerjaan lain (mis. *komunikasi*, *teliti*, *jujur*). Penting
  untuk dikuasai, tapi bukan penciri pekerjaan.
- **Selisih negatif** → skill yang justru **lebih jarang** diminta pada pekerjaan ini
  dibanding pasar umum.

**Peringatan penting saat menafsirkan.**
1. Angkanya adalah **pangsa relatif**, bukan persentase lowongan. Bila satu
   lowongan menyebut 10 skill, tiap skill menyumbang 1/10 pada penyebutnya.
2. Pekerjaan dengan jumlah lowongan sedikit menghasilkan pangsa yang tidak stabil —
   perhatikan jumlah lowongan yang tertera di bawah sebelum menarik kesimpulan.
        """)
    base = q(f"""SELECT s.name, COUNT(*) f FROM job_skills js JOIN skills s ON s.id=js.skill_id
                 WHERE s.escudero_broad_category IN {broad_sql} GROUP BY s.name""")
    total_base = base.f.sum()
    base = base.set_index("name")
    titles = q("SELECT title, COUNT(*) n FROM jobs WHERE title!='' GROUP BY title ORDER BY n DESC LIMIT 200")
    pick = st.selectbox("Bandingkan pekerjaan", titles.title.tolist())
    n_lowongan = int(titles.loc[titles.title == pick, "n"].iloc[0])
    if n_lowongan < 10:
        st.warning(f"Pekerjaan '{pick}' hanya punya {n_lowongan} lowongan. "
                  "Pangsa yang dihitung dari sampel sekecil ini tidak stabil — "
                  "tafsirkan dengan hati-hati.")
    else:
        st.caption(f"Dihitung dari {n_lowongan} lowongan berjudul '{pick}'.")
    sub = q(f"""SELECT s.name, COUNT(*) f FROM jobs j JOIN job_skills js ON js.job_id=j.id
                JOIN skills s ON s.id=js.skill_id
                WHERE j.title=? AND s.escudero_broad_category IN {broad_sql} GROUP BY s.name""", (pick,))
    if sub.empty:
        st.info("Belum ada data untuk pekerjaan ini.")
        return
    total_sub = sub.f.sum()
    sub = sub.set_index("name")
    rows = []
    for name in sub.index:
        share_sub = sub.loc[name, "f"] / total_sub
        share_base = base.loc[name, "f"] / total_base if name in base.index else 0
        rows.append((name, share_sub, share_base, share_sub - share_base))
    gap = pd.DataFrame(rows, columns=["skill", "share_pekerjaan", "share_baseline", "gap"])
    gap = gap.sort_values("gap", ascending=False).head(20)
    fig = px.bar(gap.iloc[::-1], x="gap", y="skill", orientation="h",
                 color="gap", color_continuous_scale="RdBu",
                 height=28 * len(gap) + 140,
                 labels={"gap": "Selisih Pangsa (Pekerjaan − Pasar)", "skill": "Skill"},
                 title=f"Skill paling khas untuk '{pick}' dibanding pasar keseluruhan")
    # tampilkan SEMUA label sumbu-Y; tanpa ini Plotly melewati sebagian nama skill
    fig.update_yaxes(tickmode="linear", dtick=1, automargin=True)
    st.plotly_chart(fig, use_container_width=True)

    tabel = gap.copy()
    tabel["rasio"] = tabel.apply(
        lambda r: (r.share_pekerjaan / r.share_baseline) if r.share_baseline > 0 else float("inf"),
        axis=1)
    tabel["share_pekerjaan"] = (tabel.share_pekerjaan * 100).round(2).astype(str) + "%"
    tabel["share_baseline"] = (tabel.share_baseline * 100).round(2).astype(str) + "%"
    tabel["gap"] = (tabel.gap * 100).round(2).astype(str) + " poin"
    tabel["rasio"] = tabel.rasio.map(lambda x: "baru di pekerjaan ini" if x == float("inf")
                                     else f"{x:.1f}×")
    st.dataframe(
        tabel.rename(columns={"skill": "Skill", "share_pekerjaan": "Pangsa di Pekerjaan",
                              "share_baseline": "Pangsa di Pasar", "gap": "Selisih",
                              "rasio": "Berapa Kali Lebih Menonjol"}),
        use_container_width=True, hide_index=True)
    st.caption("Kolom terakhir = Pangsa di Pekerjaan ÷ Pangsa di Pasar. Nilai 3,0× berarti "
              "skill tersebut tiga kali lebih menonjol pada pekerjaan ini dibanding rata-rata pasar.")


PAGES = {
    "Ringkasan": page_overview,
    "Jumlah Lowongan per Pekerjaan": page_job_title_summary,
    "Klasifikasi Jabatan (KBJI 2014)": page_kbji_classification,
    "Skill per Pekerjaan": page_skill_by_job,
    "Detail Kebutuhan per Pekerjaan": page_job_detail,
    "Lokasi & Pekerjaan": page_location_job_title,
    "Skill per Lokasi": page_skill_by_location,
    "Skill Teratas & Berkembang": page_top_skills,
    "Taksonomi Keterampilan": page_taxonomy,
    "Jenjang Pendidikan & Bidang Studi": page_education,
    "Skill yang Sering Muncul Bersama": page_cooccurrence,
    "Tren Permintaan Skill": page_trends,
    "Gaji yang Ditawarkan": page_salary,
    "Occupation-Specific Skills": page_skill_gap,
}

try:
    PAGES[page]()
except Exception as e:
    st.error(f"Terjadi kesalahan: {e}")
    st.info("Pastikan file DB `outputs/ner_jobposting.sqlite` sudah dibuat oleh notebook "
            "dan path DB_PATH di atas benar.")