import re
import pickle
from urllib.parse import urlparse
from collections import Counter

import streamlit as st
import numpy as np
import requests
import trafilatura
import matplotlib.pyplot as plt

from bs4 import BeautifulSoup
from Sastrawi.Stemmer.StemmerFactory import StemmerFactory


# ============================================================
# KONFIGURASI HALAMAN
# ============================================================

st.set_page_config(
    page_title="Klasifikasi Berita",
    page_icon="📰",
    layout="wide"
)


# ============================================================
# LOAD MODEL
# ============================================================

MODEL_PATH = "model.pkl"


@st.cache_resource
def load_model():
    with open(MODEL_PATH, "rb") as file:
        return pickle.load(file)


try:
    package = load_model()

    model_w2v = package["word2vec"]
    model_nb = package["naive_bayes"]
    stopwords = set(package["stopwords"])
    vector_size = package["vector_size"]

except FileNotFoundError:
    st.error(
        "File model.pkl tidak ditemukan. "
        "Jalankan notebook UTS terlebih dahulu sampai bagian penyimpanan model.pkl."
    )
    st.stop()

except Exception as error:
    st.error(
        f"Gagal memuat model.pkl: {error}"
    )
    st.stop()


# ============================================================
# STEMMER
# ============================================================

@st.cache_resource
def load_stemmer():
    factory = StemmerFactory()
    return factory.create_stemmer()


stemmer = load_stemmer()


# ============================================================
# FUNGSI CRAWLING
# ============================================================

def crawl_berita(url):
    """
    Mengambil isi artikel dari URL menggunakan Trafilatura.
    Jika gagal, menggunakan BeautifulSoup sebagai fallback.
    """

    try:
        downloaded = trafilatura.fetch_url(url)

        if downloaded:

            text = trafilatura.extract(
                downloaded,
                include_comments=False,
                include_tables=False
            )

            if text and len(text.strip()) >= 100:
                return text.strip()

    except Exception:
        pass


    try:

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/154.0.0.0 Safari/537.36"
            )
        }

        response = requests.get(
            url,
            headers=headers,
            timeout=20
        )

        response.raise_for_status()

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        for tag in soup(
            [
                "script",
                "style",
                "noscript",
                "nav",
                "footer",
                "header"
            ]
        ):
            tag.decompose()

        paragraphs = []

        for paragraph in soup.find_all("p"):

            text = paragraph.get_text(
                " ",
                strip=True
            )

            if text:
                paragraphs.append(text)

        result = " ".join(paragraphs)

        if len(result) < 100:
            raise ValueError(
                "Isi artikel terlalu pendek atau tidak berhasil ditemukan."
            )

        return result

    except Exception as error:

        raise RuntimeError(
            f"Gagal mengambil isi berita: {error}"
        )


# ============================================================
# PREPROCESSING
# ============================================================

def preprocess_text(text):
    """
    Preprocessing untuk teks berita hasil crawling.
    """

    text = str(text).lower()

    text = re.sub(
        r"\d+",
        " ",
        text
    )

    text = re.sub(
        r"[^a-zA-ZÀ-ÿ\s]",
        " ",
        text
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    ).strip()

    tokens = text.split()

    text_stemmed = stemmer.stem(
        " ".join(tokens)
    )

    tokens = text_stemmed.split()

    tokens = [
        token
        for token in tokens
        if token not in stopwords
        and len(token) > 1
    ]

    return tokens


# ============================================================
# DOCUMENT VECTOR
# ============================================================

def document_vector(tokens):

    vectors = [
        model_w2v.wv[token]
        for token in tokens
        if token in model_w2v.wv
    ]

    if not vectors:
        return np.zeros(
            vector_size
        )

    return np.mean(
        vectors,
        axis=0
    )


# ============================================================
# PREDIKSI
# ============================================================

def predict_text(text):

    tokens = preprocess_text(text)

    known_tokens = [
        token
        for token in tokens
        if token in model_w2v.wv
    ]

    if not known_tokens:

        return (
            None,
            {},
            tokens,
            0
        )

    vector = document_vector(
        tokens
    )

    vector = vector.reshape(
        1,
        -1
    )

    prediction = model_nb.predict(
        vector
    )[0]

    probabilities = model_nb.predict_proba(
        vector
    )[0]

    classes = model_nb.classes_

    probability_dict = {
        str(label): float(probability)
        for label, probability in zip(
            classes,
            probabilities
        )
    }

    return (
        prediction,
        probability_dict,
        tokens,
        len(known_tokens)
    )


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:

    st.title(
        "📰 Klasifikasi Berita"
    )

    st.markdown(
        """
        **Metode**

        - Word Embedding
        - Word2Vec Skip-gram
        - Mean Pooling
        - Gaussian Naive Bayes

        **Kelas**

        - 🏆 Sport
        - 💰 Finance
        """
    )

    st.divider()

    st.caption(
        "Model: UTS PPW"
    )

    st.caption(
        f"Vocabulary: {len(model_w2v.wv):,} kata"
    )

    st.caption(
        f"Embedding: {vector_size} dimensi"
    )


# ============================================================
# HEADER
# ============================================================

st.title(
    "📰 Klasifikasi Teks Berita"
)

st.markdown(
    """
    ### Word Embedding Skip-gram + Naive Bayes

    Masukkan **link berita** untuk mengambil isi artikel secara langsung,
    kemudian sistem akan menentukan apakah berita tersebut termasuk
    **Sport** atau **Finance**.
    """
)


# ============================================================
# INPUT URL
# ============================================================

st.subheader(
    "🔗 Live Crawl Berita"
)

url = st.text_input(
    "Masukkan URL berita",
    placeholder="https://contoh.com/berita..."
)

col1, col2 = st.columns(
    [1, 5]
)

with col1:

    classify_button = st.button(
        "🔍 Klasifikasikan",
        type="primary",
        use_container_width=True
    )


# ============================================================
# PROSES KLASIFIKASI URL
# ============================================================

if classify_button:

    # ========================================================
    # VALIDASI URL
    # ========================================================

    if not url.strip():

        st.warning(
            "Masukkan URL berita terlebih dahulu."
        )

        st.stop()


    parsed = urlparse(
        url
    )


    if parsed.scheme not in [
        "http",
        "https"
    ]:

        st.error(
            "URL harus diawali http:// atau https://"
        )

        st.stop()


    # ========================================================
    # CRAWLING
    # ========================================================

    with st.spinner(
        "Mengambil isi berita dari URL..."
    ):

        try:

            article_text = crawl_berita(
                url
            )

        except Exception as error:

            st.error(
                f"Gagal mengambil berita: {error}"
            )

            st.stop()


    st.success(
        f"Berhasil mengambil berita dari {parsed.netloc}"
    )


    # ========================================================
    # ISI BERITA
    # ========================================================

    st.subheader(
        "📄 Isi Berita"
    )

    with st.expander(
        "Lihat isi berita",
        expanded=True
    ):

        st.write(
            article_text
        )


    # ========================================================
    # PREDIKSI
    # ========================================================

    with st.spinner(
        "Melakukan preprocessing dan klasifikasi..."
    ):

        (
            prediction,
            probabilities,
            tokens,
            known_token_count
        ) = predict_text(
            article_text
        )


    if prediction is None:

        st.error(
            "Tidak ada kata yang dikenali oleh vocabulary model. "
            "Coba gunakan artikel lain."
        )

        st.stop()


    # ========================================================
    # HASIL KLASIFIKASI
    # ========================================================

    st.divider()

    st.subheader(
        "🎯 Hasil Klasifikasi"
    )


    if prediction == "sport":

        st.success(
            "🏆 BERITA SPORT"
        )

    elif prediction == "finance":

        st.success(
            "💰 BERITA FINANCE"
        )

    else:

        st.info(
            f"Prediksi: {str(prediction).upper()}"
        )


    # ========================================================
    # PROBABILITAS
    # ========================================================

    st.subheader(
        "📊 Probabilitas Prediksi"
    )


    finance_probability = probabilities.get(
        "finance",
        0
    )

    sport_probability = probabilities.get(
        "sport",
        0
    )


    col1, col2 = st.columns(
        2
    )


    with col1:

        st.metric(
            "💰 Finance",
            f"{finance_probability * 100:.2f}%"
        )

        st.progress(
            min(
                max(
                    finance_probability,
                    0.0
                ),
                1.0
            )
        )


    with col2:

        st.metric(
            "🏆 Sport",
            f"{sport_probability * 100:.2f}%"
        )

        st.progress(
            min(
                max(
                    sport_probability,
                    0.0
                ),
                1.0
            )
        )


    # ========================================================
    # DETAIL PEMROSESAN
    # ========================================================

    st.divider()

    st.subheader(
        "🔎 Detail Pemrosesan"
    )


    total_characters = len(
        article_text
    )

    total_tokens = len(
        tokens
    )

    known_tokens = known_token_count

    unknown_tokens = (
        total_tokens
        - known_tokens
    )


    known_percentage = (
        known_tokens
        / total_tokens
        * 100
        if total_tokens > 0
        else 0
    )


    unknown_percentage = (
        unknown_tokens
        / total_tokens
        * 100
        if total_tokens > 0
        else 0
    )


    # ========================================================
    # METRIK PEMROSESAN
    # ========================================================

    col1, col2, col3, col4 = st.columns(
        4
    )


    with col1:

        st.metric(
            "Jumlah karakter",
            f"{total_characters:,}"
        )


    with col2:

        st.metric(
            "Jumlah token",
            f"{total_tokens:,}"
        )


    with col3:

        st.metric(
            "Token dikenal model",
            f"{known_tokens:,}"
        )


    with col4:

        st.metric(
            "Token tidak dikenal",
            f"{unknown_tokens:,}"
        )


    # ========================================================
    # VISUALISASI TOKEN
    # ========================================================

    st.subheader(
        "📊 Visualisasi Token"
    )


    col1, col2 = st.columns(
        2
    )


    # ========================================================
    # GRAFIK BATANG TOKEN
    # ========================================================

    with col1:

        fig, ax = plt.subplots(
            figsize=(6, 4)
        )


        labels = [
            "Total Token",
            "Dikenal Model",
            "Tidak Dikenal"
        ]


        values = [
            total_tokens,
            known_tokens,
            unknown_tokens
        ]


        bars = ax.bar(
            labels,
            values
        )


        ax.set_title(
            "Jumlah Token Hasil Preprocessing"
        )


        ax.set_ylabel(
            "Jumlah Token"
        )


        ax.grid(
            axis="y",
            alpha=0.3
        )


        for bar, value in zip(
            bars,
            values
        ):

            ax.text(
                bar.get_x()
                + bar.get_width() / 2,
                value + 1,
                str(value),
                ha="center"
            )


        plt.tight_layout()

        st.pyplot(
            fig
        )

        plt.close(
            fig
        )


    # ========================================================
    # PIE CHART TOKEN
    # ========================================================

    with col2:

        fig, ax = plt.subplots(
            figsize=(6, 4)
        )


        labels = [
            "Dikenal Model",
            "Tidak Dikenal"
        ]


        values = [
            known_tokens,
            unknown_tokens
        ]


        ax.pie(
            values,
            labels=labels,
            autopct="%1.1f%%",
            startangle=90
        )


        ax.set_title(
            "Proporsi Vocabulary Word2Vec"
        )


        plt.tight_layout()

        st.pyplot(
            fig
        )

        plt.close(
            fig
        )


    st.caption(
        f"Sebanyak {known_tokens} dari {total_tokens} token "
        f"({known_percentage:.2f}%) dikenali oleh vocabulary "
        f"Word2Vec, sedangkan {unknown_tokens} token "
        f"({unknown_percentage:.2f}%) tidak dikenali."
    )


    # ========================================================
    # VISUALISASI KATA
    # ========================================================

    st.subheader(
        "🔤 Frekuensi Kata"
    )


    word_frequency = Counter(
        tokens
    )


    top_words = word_frequency.most_common(
        10
    )


    words = [
        item[0]
        for item in top_words
    ]


    frequencies = [
        item[1]
        for item in top_words
    ]


    # ========================================================
    # GRAFIK 10 KATA TERATAS
    # ========================================================

    if top_words:

        fig, ax = plt.subplots(
            figsize=(10, 5)
        )


        bars = ax.bar(
            words,
            frequencies
        )


        ax.set_title(
            "10 Kata yang Paling Sering Muncul"
        )


        ax.set_xlabel(
            "Kata"
        )


        ax.set_ylabel(
            "Frekuensi"
        )


        ax.tick_params(
            axis="x",
            rotation=45
        )


        ax.grid(
            axis="y",
            alpha=0.3
        )


        for bar, value in zip(
            bars,
            frequencies
        ):

            ax.text(
                bar.get_x()
                + bar.get_width() / 2,
                value + 0.05,
                str(value),
                ha="center"
            )


        plt.tight_layout()

        st.pyplot(
            fig
        )

        plt.close(
            fig
        )


    # ========================================================
    # STATUS VOCABULARY WORD2VEC
    # ========================================================

    st.subheader(
        "🔤 Status Vocabulary Word2Vec"
    )


    known_word_frequency = Counter(
        token
        for token in tokens
        if token in model_w2v.wv
    )


    unknown_word_frequency = Counter(
        token
        for token in tokens
        if token not in model_w2v.wv
    )


    col1, col2 = st.columns(
        2
    )


    # ========================================================
    # KATA DIKENAL
    # ========================================================

    with col1:

        st.markdown(
            "### ✅ Token Dikenal"
        )


        known_top_words = (
            known_word_frequency
            .most_common(10)
        )


        if known_top_words:

            for word, frequency in known_top_words:

                st.write(
                    f"**{word}** — "
                    f"{frequency} kali"
                )

        else:

            st.write(
                "Tidak ada token yang dikenal."
            )


    # ========================================================
    # KATA TIDAK DIKENAL
    # ========================================================

    with col2:

        st.markdown(
            "### ❌ Token Tidak Dikenal"
        )


        unknown_top_words = (
            unknown_word_frequency
            .most_common(10)
        )


        if unknown_top_words:

            for word, frequency in unknown_top_words:

                st.write(
                    f"**{word}** — "
                    f"{frequency} kali"
                )

        else:

            st.write(
                "Semua token dikenali model."
            )


    # ========================================================
    # TOKEN HASIL PREPROCESSING
    # ========================================================

    st.subheader(
        "🧹 Token Hasil Preprocessing"
    )


    with st.expander(
        "Lihat seluruh token hasil preprocessing"
    ):

        st.write(
            " ".join(
                tokens
            )
        )


    # ========================================================
    # KETERANGAN MODEL
    # ========================================================

    st.info(
        "Prediksi dihasilkan dari document vector yang diperoleh "
        "dengan Mean Pooling embedding Word2Vec Skip-gram, kemudian "
        "diklasifikasikan menggunakan Gaussian Naive Bayes."
    )


# ============================================================
# MODE INPUT TEKS MANUAL
# ============================================================

st.divider()

st.subheader(
    "✍️ Uji Teks Manual"
)

st.caption(
    "Bagian ini opsional untuk menguji model tanpa melakukan crawling URL."
)


manual_text = st.text_area(
    "Masukkan isi berita",
    height=180,
    placeholder="Tempel isi berita di sini..."
)


if st.button(
    "Klasifikasikan Teks",
    key="manual_predict"
):

    if not manual_text.strip():

        st.warning(
            "Masukkan teks berita terlebih dahulu."
        )

    else:

        (
            manual_prediction,
            manual_probabilities,
            manual_tokens,
            manual_known_count
        ) = predict_text(
            manual_text
        )


        if manual_prediction is None:

            st.error(
                "Tidak ada kata yang dikenali oleh vocabulary model."
            )

        else:

            if manual_prediction == "sport":

                st.success(
                    "🏆 BERITA SPORT"
                )

            elif manual_prediction == "finance":

                st.success(
                    "💰 BERITA FINANCE"
                )

            else:

                st.info(
                    f"Prediksi: "
                    f"{str(manual_prediction).upper()}"
                )


            st.write(
                f"Finance: "
                f"{manual_probabilities.get('finance', 0) * 100:.2f}%"
            )


            st.write(
                f"Sport: "
                f"{manual_probabilities.get('sport', 0) * 100:.2f}%"
            )


            st.caption(
                f"Token hasil preprocessing: "
                f"{len(manual_tokens)}"
            )


            st.caption(
                f"Token dikenal model: "
                f"{manual_known_count}"
            )


# ============================================================
# FOOTER
# ============================================================

st.divider()

st.caption(
    "UTS Pencarian dan Penambangan Web — "
    "Word2Vec Skip-gram + Gaussian Naive Bayes"
)