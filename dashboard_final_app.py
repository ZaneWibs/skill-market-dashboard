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
# (v14) Klasifikasi Jabatan ke Golongan Pokok KBJI 2014 (Bagian 8d notebook).
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
# berganti warna saat memilih jabatan/lokasi yang berbeda.
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
def get_conn(path):
    return sqlite3.connect(path, check_same_thread=False)


@st.cache_data
def q(sql, params=()):
    return pd.read_sql(sql, get_conn(DB_PATH), params=params)


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
    sehingga warnanya tidak berubah saat memilih jabatan/lokasi berbeda)."""
    palette = getattr(px.colors.qualitative, palette_name)
    values = sorted(set(v for v in values if v is not None))
    return {v: palette[i % len(palette)] for i, v in enumerate(values)}


# ------------------------------------------------------------------ sidebar
st.sidebar.title("🔎 Skill Market")
page = st.sidebar.radio("Halaman", [
    "Ringkasan",
    "Jumlah Lowongan per Jabatan",
    "Klasifikasi Jabatan (KBJI 2014)",
    "Skill per Jabatan",
    "Detail Kebutuhan per Jabatan",
    "Lokasi & Jabatan",
    "Skill per Lokasi",
    "Skill Teratas & Berkembang",
    "Taksonomi Keterampilan",
    "Jenjang Pendidikan & Bidang Studi",
    "Skill yang Sering Muncul Bersama",
    "Tren Permintaan Skill",
    "Analisis Kesenjangan Skill",
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
st.sidebar.markdown("**🗂️ Legenda Golongan Pokok KBJI**")
with st.sidebar.expander("Lihat semua warna golongan"):
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
    st.title("📋 Jumlah Lowongan per Jabatan")
    st.caption("Seluruh jabatan yang ada beserta jumlah lowongannya, diurutkan dari yang terbanyak.")
    df = q("""SELECT title, COUNT(*) n FROM jobs
              WHERE title != '' GROUP BY title ORDER BY n DESC""")
    cari = st.text_input("Cari nama jabatan (opsional)", "")
    if cari:
        df = df[df.title.str.contains(cari, case=False, na=False)]
    view, info = paginate(df, "jobtitle_summary")
    st.caption(info)
    view = view.rename(columns={"title": "Jabatan", "n": "Jumlah Lowongan"})
    view.index = view.index + 1
    st.dataframe(view, use_container_width=True)


def page_kbji_classification():
    st.title("🗂️ Klasifikasi Jabatan (KBJI 2014)")
    st.caption("Setiap judul Pekerjaan diklasifikasikan ke salah satu dari 9 Golongan Pokok "
              "KBJI 2014 (kode 1-9; TNI/POLRI dikecualikan). Metode: lexicon → fuzzy → k-NN "
              "embedding terhadap 2.155 nama jabatan riil dari dokumen KBJI. Lihat Bagian 8d "
              "pada notebook untuk detail metodologi.")

    dist = q("""SELECT kbji_golongan_pokok_nama AS golongan, COUNT(*) n,
                       AVG(kbji_confidence) conf_rata
                FROM jobs GROUP BY golongan ORDER BY n DESC""")
    dist["golongan"] = pd.Categorical(dist["golongan"],
                                      categories=[g for g in KBJI_ORDER if g in dist.golongan.values],
                                      ordered=True)
    dist = dist.sort_values("golongan")

    c1, c2, c3 = st.columns(3)
    c1.metric("Total lowongan", f"{dist.n.sum():,}")
    n_unclass = int(dist.loc[dist.golongan == "Tidak Terklasifikasi", "n"].sum()) \
        if "Tidak Terklasifikasi" in dist.golongan.values else 0
    c2.metric("Tidak terklasifikasi", f"{n_unclass:,}",
             f"{n_unclass / dist.n.sum():.1%}" if dist.n.sum() else "0%")
    c3.metric("Rata-rata confidence", f"{(dist.n * dist.conf_rata).sum() / dist.n.sum():.2f}")

    _kolom_jobs = q("SELECT * FROM jobs LIMIT 1").columns.tolist()
    if "kbji_source" in _kolom_jobs:
        _man = q("SELECT COUNT(*) n FROM jobs WHERE kbji_source='manual_review'").n[0]
        if _man:
            st.info(f"{_man} lowongan telah dikoreksi manual berdasarkan telaah pembimbing "
                   "(lihat `kbji_override.py` untuk daftar koreksi beserta alasannya). "
                   "Sisanya hasil klasifikasi otomatis.")

    st.subheader("Distribusi Lowongan per Golongan Pokok")
    st.plotly_chart(px.bar(dist, x="golongan", y="n", color="golongan",
                    color_discrete_map=KBJI_COLORS,
                    labels={"golongan": "Golongan Pokok", "n": "Jumlah Lowongan"}),
                    use_container_width=True)

    tab1, tab2 = st.tabs(["Jelajah per Golongan", "Kualitas Klasifikasi (QA)"])

    with tab1:
        pilihan = [g for g in KBJI_ORDER if g in dist.golongan.values]
        pick = st.selectbox("Pilih golongan pokok", pilihan)
        df = q("""SELECT title AS jabatan, COUNT(*) n, AVG(kbji_confidence) conf
                 FROM jobs WHERE kbji_golongan_pokok_nama = ?
                 GROUP BY title ORDER BY n DESC""", (pick,))
        view, info = paginate(df, "kbji_jelajah")
        st.caption(info)
        _top = view.head(20)
        _fig = px.bar(_top.iloc[::-1], x="n", y="jabatan", orientation="h",
                      height=30 * len(_top) + 150,
                      color_discrete_sequence=[KBJI_COLORS.get(pick, "#6366F1")],
                      labels={"n": "Jumlah Lowongan", "jabatan": "Jabatan"},
                      title=f"Jabatan teratas dalam golongan '{pick}'")
        # Tanpa baris ini Plotly menyembunyikan sebagian nama jabatan ketika
        # batangnya rapat -- itulah sebab ada batang tanpa label pada tangkapan
        # layar Bu Tri.
        _fig.update_yaxes(tickmode="linear", dtick=1, automargin=True)
        _fig.update_xaxes(dtick=1)
        st.plotly_chart(_fig, use_container_width=True)
        st.dataframe(
            view.rename(columns={"jabatan": "Jabatan", "n": "Jumlah Lowongan", "conf": "Confidence Rata-rata"}),
            use_container_width=True, hide_index=True)

    with tab2:
        st.caption("Klasifikasi dengan confidence rendah lebih berisiko salah -- berguna untuk "
                  "spot-check manual atau menambah kata kunci lexicon di notebook.")
        low = q("""SELECT title AS jabatan, kbji_golongan_pokok_nama AS golongan, kbji_confidence AS conf
                  FROM jobs WHERE title != '' GROUP BY title
                  ORDER BY conf ASC LIMIT 100""")
        st.dataframe(
            low.rename(columns={"jabatan": "Jabatan", "golongan": "Golongan Pokok", "conf": "Confidence"}),
            use_container_width=True, hide_index=True)


def page_skill_by_job():
    st.title("💼 Skill per Jabatan")
    titles = q("""SELECT title, COUNT(*) n FROM jobs
                  WHERE title != '' GROUP BY title ORDER BY n DESC LIMIT 300""")
    pick = st.selectbox("Pilih jabatan", titles.title.tolist())
    df = q(f"""SELECT s.name, s.label, s.escudero_subcategory, COUNT(*) freq
              FROM jobs j JOIN job_skills js ON js.job_id = j.id
              JOIN skills s ON s.id = js.skill_id
              WHERE j.title = ? AND s.escudero_broad_category IN {broad_sql}
              GROUP BY s.name, s.label ORDER BY freq DESC LIMIT 25""", (pick,))
    if df.empty:
        st.info("Belum ada skill tercatat untuk jabatan ini.")
    else:
        st.plotly_chart(px.bar(df.iloc[::-1], x="freq", y="name", color="escudero_subcategory",
                        orientation="h", color_discrete_map=ESCUDERO_SUB_COLORS,
                        labels={"freq": "Jumlah Lowongan", "name": "Skill", "escudero_subcategory": "Subkategori"}),
                        use_container_width=True)


def page_job_detail():
    st.title("🧭 Detail Kebutuhan per Jabatan")
    st.caption("Untuk jabatan terpilih: skill lengkap dengan taksonomi Layer 2 "
              "(domain, transferability, importance, proficiency), tools, jenjang pendidikan, "
              "dan bidang studi yang diminta.")
    titles = q("""SELECT title, COUNT(*) n FROM jobs WHERE title != ''
                  GROUP BY title ORDER BY n DESC LIMIT 300""")
    pick = st.selectbox("Pilih jabatan", titles.title.tolist())
    n_job = int(titles.loc[titles.title == pick, "n"].iloc[0])
    st.markdown(f"### {pick} · {n_job} lowongan")

    # (v14) Golongan Pokok KBJI 2014 untuk jabatan ini
    kbji_info = q("""SELECT kbji_golongan_pokok_nama, kbji_confidence FROM jobs
                     WHERE title = ? LIMIT 1""", (pick,))
    if not kbji_info.empty:
        gnama = kbji_info.kbji_golongan_pokok_nama.iloc[0]
        gconf = kbji_info.kbji_confidence.iloc[0]
        gclr = KBJI_COLORS.get(gnama, "#94A3B8")
        st.markdown(
            f'🗂️ Golongan Pokok KBJI: <span style="background-color:{gclr}22; '
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
        st.info("Belum ada skill tercatat untuk jabatan ini.")
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

    # ---- Ringkasan taksonomi jabatan ini ----
    st.subheader("🧬 Profil Taksonomi Jabatan Ini")
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
    st.title("📍🗂️ Lokasi & Jabatan")
    tab1, tab2 = st.tabs(["Pilih Lokasi", "Ringkasan Semua Lokasi"])

    with tab1:
        st.caption("Pilih satu lokasi untuk melihat semua jabatan yang ada di sana, "
                  "diurutkan dari jumlah lowongan terbanyak.")
        locs = q("""SELECT l.name, COUNT(*) n FROM jobs j JOIN locations l ON l.id=j.location_id
                    WHERE l.name != '' GROUP BY l.name ORDER BY n DESC LIMIT 300""")
        pick = st.selectbox("Pilih lokasi", locs.name.tolist(), key="locjob_pick")
        df = q("""SELECT j.title, COUNT(*) n FROM jobs j JOIN locations l ON l.id=j.location_id
                  WHERE l.name=? AND j.title!='' GROUP BY j.title ORDER BY n DESC""", (pick,))
        if df.empty:
            st.info("Belum ada data jabatan untuk lokasi ini.")
        else:
            st.metric(f"Total lowongan di '{pick}'", f"{df.n.sum():,}")
            view, info = paginate(df, "locjob_detail", default_per_page=25)
            st.caption(info)
            st.plotly_chart(
                px.bar(view.iloc[::-1], x="n", y="title", orientation="h",
                      height=25 * len(view) + 140,
                      labels={"n": "Jumlah Lowongan", "title": "Jabatan"},
                      title=f"Jabatan di '{pick}'"),
                use_container_width=True)
            st.dataframe(
                view.rename(columns={"title": "Jabatan", "n": "Jumlah Lowongan"}),
                use_container_width=True, hide_index=True)

    with tab2:
        st.caption("Satu baris per lokasi: total lowongan dan jumlah jabatan unik di sana. "
                  "Bisa diurutkan dari lowongan terbanyak ATAU variasi jabatan terbanyak.")
        ring = q("""SELECT l.name AS lokasi, COUNT(*) AS total_lowongan,
                          COUNT(DISTINCT j.title) AS jumlah_jabatan_unik
                   FROM jobs j JOIN locations l ON l.id = j.location_id
                   WHERE l.name != '' GROUP BY l.name""")
        urut = st.radio("Urutkan berdasarkan",
                        ["Total Lowongan Terbanyak", "Variasi Jabatan Terbanyak"],
                        horizontal=True, key="locjob_ringkasan_urut")
        kolom = "total_lowongan" if urut == "Total Lowongan Terbanyak" else "jumlah_jabatan_unik"
        ring = ring.sort_values(kolom, ascending=False)
        view, info = paginate(ring, "locjob_ringkasan")
        st.caption(info)
        st.dataframe(
            view.rename(columns={"lokasi": "Lokasi", "total_lowongan": "Total Lowongan",
                                 "jumlah_jabatan_unik": "Jabatan Unik"}),
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

    st.subheader("Peta Kategori Escudero × Golongan Pokok KBJI")
    st.caption("Kategori skill apa yang paling dibutuhkan di tiap golongan pekerjaan.")
    hm2 = q(f"""SELECT j.kbji_golongan_pokok_nama AS golongan, s.escudero_broad_category AS kategori, COUNT(*) n
               FROM jobs j JOIN job_skills js ON js.job_id=j.id JOIN skills s ON s.id=js.skill_id
               WHERE s.escudero_broad_category IN {broad_sql} AND j.kbji_golongan_pokok_nama IS NOT NULL
               GROUP BY golongan, kategori""")
    if not hm2.empty:
        pivot2 = hm2.pivot_table(index="golongan", columns="kategori", values="n", fill_value=0)
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
def cooccurrence(broad_sql, min_count):
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
    df = cooccurrence(label_sql, min_c).head(40)
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
def bulan_valid():
    """Bulan yang punya cukup lowongan untuk dianalisis trennya."""
    d = q("""SELECT substr(posted_date,1,7) bulan, COUNT(*) n FROM jobs
             WHERE posted_date NOT IN ('','None') GROUP BY bulan ORDER BY bulan""")
    d = d[(d.bulan >= TREN_BULAN_MIN) & (d.bulan <= TREN_BULAN_MAX)
          & (d.n >= TREN_MIN_LOWONGAN_PER_BULAN)]
    return d


def page_trends():
    st.title("📈 Tren Permintaan Skill")

    bv = bulan_valid()
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


def page_skill_gap():
    st.title("🎯 Analisis Kesenjangan Skill")
    st.caption("Membandingkan seberapa besar porsi suatu skill di SATU jabatan "
              "dibandingkan porsinya di SELURUH pasar kerja.")

    with st.expander("📖 Cara membaca halaman ini (klik untuk membuka)", expanded=True):
        st.markdown("""
**Apa yang dihitung.** Untuk setiap skill dilakukan perbandingan dua proporsi:

| Kolom | Rumus | Artinya |
|---|---|---|
| **Pangsa di Jabatan** | jumlah penyebutan skill di jabatan ini ÷ total penyebutan semua skill di jabatan ini | Dari 100 skill yang diminta lowongan jabatan ini, berapa yang berupa skill tersebut |
| **Pangsa di Pasar** | jumlah penyebutan skill di seluruh lowongan ÷ total penyebutan semua skill di seluruh lowongan | Angka pembanding (*baseline*): seberapa umum skill itu di pasar kerja secara keseluruhan |
| **Selisih** | Pangsa di Jabatan − Pangsa di Pasar | Seberapa **khas** skill itu bagi jabatan tersebut |

**Contoh angka.** Misalkan untuk jabatan *Data Analyst*: `microsoft excel` punya
Pangsa di Jabatan 0,082 (8,2%), Pangsa di Pasar 0,017 (1,7%), Selisih +0,065.
Dibacanya: *Excel menyusun 8,2% dari seluruh permintaan skill pada lowongan Data
Analyst, sementara di pasar kerja secara umum hanya 1,7%. Jadi Excel 4,8 kali
lebih menonjol pada jabatan ini daripada rata-rata pasar.*

**Cara membaca tandanya.**
- **Selisih positif besar** → skill pembeda (*distinctive*). Inilah yang membuat
  jabatan tersebut berbeda dari jabatan lain, dan yang paling relevan untuk
  rekomendasi kurikulum atau pelatihan yang spesifik.
- **Selisih mendekati nol** → skill generik. Diminta jabatan ini, tapi sama
  seringnya diminta jabatan lain (mis. *komunikasi*, *teliti*, *jujur*). Penting
  untuk dikuasai, tapi bukan penciri jabatan.
- **Selisih negatif** → skill yang justru **lebih jarang** diminta pada jabatan ini
  dibanding pasar umum.

**Peringatan penting saat menafsirkan.**
1. Ini mengukur **kekhasan**, bukan **kekurangan tenaga kerja**. "Kesenjangan"
   di sini adalah selisih antara jabatan dan pasar pada sisi *permintaan* saja.
   Untuk menyimpulkan adanya kesenjangan keterampilan yang sesungguhnya,
   diperlukan data sisi *penawaran* (mis. profil lulusan), yang tidak tersedia
   dalam data lowongan ini.
2. Angkanya adalah **pangsa relatif**, bukan persentase lowongan. Bila satu
   lowongan menyebut 10 skill, tiap skill menyumbang 1/10 pada penyebutnya.
3. Jabatan dengan jumlah lowongan sedikit menghasilkan pangsa yang tidak stabil —
   perhatikan jumlah lowongan yang tertera di bawah sebelum menarik kesimpulan.
        """)
    base = q(f"""SELECT s.name, COUNT(*) f FROM job_skills js JOIN skills s ON s.id=js.skill_id
                 WHERE s.escudero_broad_category IN {broad_sql} GROUP BY s.name""")
    total_base = base.f.sum()
    base = base.set_index("name")
    titles = q("SELECT title, COUNT(*) n FROM jobs WHERE title!='' GROUP BY title ORDER BY n DESC LIMIT 200")
    pick = st.selectbox("Bandingkan jabatan", titles.title.tolist())
    n_lowongan = int(titles.loc[titles.title == pick, "n"].iloc[0])
    if n_lowongan < 10:
        st.warning(f"Jabatan '{pick}' hanya punya {n_lowongan} lowongan. "
                  "Pangsa yang dihitung dari sampel sekecil ini tidak stabil — "
                  "tafsirkan dengan hati-hati.")
    else:
        st.caption(f"Dihitung dari {n_lowongan} lowongan berjudul '{pick}'.")
    sub = q(f"""SELECT s.name, COUNT(*) f FROM jobs j JOIN job_skills js ON js.job_id=j.id
                JOIN skills s ON s.id=js.skill_id
                WHERE j.title=? AND s.escudero_broad_category IN {broad_sql} GROUP BY s.name""", (pick,))
    if sub.empty:
        st.info("Belum ada data untuk jabatan ini.")
        return
    total_sub = sub.f.sum()
    sub = sub.set_index("name")
    rows = []
    for name in sub.index:
        share_sub = sub.loc[name, "f"] / total_sub
        share_base = base.loc[name, "f"] / total_base if name in base.index else 0
        rows.append((name, share_sub, share_base, share_sub - share_base))
    gap = pd.DataFrame(rows, columns=["skill", "share_jabatan", "share_baseline", "gap"])
    gap = gap.sort_values("gap", ascending=False).head(20)
    fig = px.bar(gap.iloc[::-1], x="gap", y="skill", orientation="h",
                 color="gap", color_continuous_scale="RdBu",
                 height=28 * len(gap) + 140,
                 labels={"gap": "Selisih Pangsa (Jabatan − Pasar)", "skill": "Skill"},
                 title=f"Skill paling khas untuk '{pick}' dibanding pasar keseluruhan")
    # tampilkan SEMUA label sumbu-Y; tanpa ini Plotly melewati sebagian nama skill
    fig.update_yaxes(tickmode="linear", dtick=1, automargin=True)
    st.plotly_chart(fig, use_container_width=True)

    tabel = gap.copy()
    tabel["rasio"] = tabel.apply(
        lambda r: (r.share_jabatan / r.share_baseline) if r.share_baseline > 0 else float("inf"),
        axis=1)
    tabel["share_jabatan"] = (tabel.share_jabatan * 100).round(2).astype(str) + "%"
    tabel["share_baseline"] = (tabel.share_baseline * 100).round(2).astype(str) + "%"
    tabel["gap"] = (tabel.gap * 100).round(2).astype(str) + " poin"
    tabel["rasio"] = tabel.rasio.map(lambda x: "baru di jabatan ini" if x == float("inf")
                                     else f"{x:.1f}×")
    st.dataframe(
        tabel.rename(columns={"skill": "Skill", "share_jabatan": "Pangsa di Jabatan",
                              "share_baseline": "Pangsa di Pasar", "gap": "Selisih",
                              "rasio": "Berapa Kali Lebih Menonjol"}),
        use_container_width=True, hide_index=True)
    st.caption("Kolom terakhir = Pangsa di Jabatan ÷ Pangsa di Pasar. Nilai 3,0× berarti "
              "skill tersebut tiga kali lebih menonjol pada jabatan ini dibanding rata-rata pasar.")


PAGES = {
    "Ringkasan": page_overview,
    "Jumlah Lowongan per Jabatan": page_job_title_summary,
    "Klasifikasi Jabatan (KBJI 2014)": page_kbji_classification,
    "Skill per Jabatan": page_skill_by_job,
    "Detail Kebutuhan per Jabatan": page_job_detail,
    "Lokasi & Jabatan": page_location_job_title,
    "Skill per Lokasi": page_skill_by_location,
    "Skill Teratas & Berkembang": page_top_skills,
    "Taksonomi Keterampilan": page_taxonomy,
    "Jenjang Pendidikan & Bidang Studi": page_education,
    "Skill yang Sering Muncul Bersama": page_cooccurrence,
    "Tren Permintaan Skill": page_trends,
    "Analisis Kesenjangan Skill": page_skill_gap,
}

try:
    PAGES[page]()
except Exception as e:
    st.error(f"Terjadi kesalahan: {e}")
    st.info("Pastikan file DB `outputs/ner_jobposting.sqlite` sudah dibuat oleh notebook "
            "dan path DB_PATH di atas benar.")