import streamlit as st
import schedule
import threading
import time
import requests
from wordcloud import WordCloud
from bs4 import BeautifulSoup
from pymongo import MongoClient
from datetime import datetime
from collections import Counter
from Sastrawi.StopWordRemover.StopWordRemoverFactory import StopWordRemoverFactory
from nltk.tokenize import word_tokenize
import nltk
import pandas as pd
import matplotlib.pyplot as plt

# Cek dan download punkt jika belum tersedia
try:
    nltk.data.find("tokenizers/punkt")
except LookupError:
    nltk.download("punkt")

# MongoDB Atlas URI (Ganti username & password dengan milikmu)
MONGO_URI = "mongodb+srv://<db_username>:<db_password>@cluster0.sy9m5us.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"

custom_stopwords = [
    "menjadi", "lebih", "banyak", "memiliki", "dapat", "akan", "dengan",
    "adalah", "karena", "juga", "seperti", "dalam", "yang", "untuk", "oleh",
    "sudah", "masih", "namun", "hingga", "tanpa", "pada", "bahwa", "agar", "berbagai", "orang", 
    "memberikan","kompasiana","komentar","selanjutnya","tersebut"
]

def save_to_mongodb(data, db_name="artikel_db", collection_name="scraping"):
    client = MongoClient(MONGO_URI)
    db = client[db_name]
    collection = db[collection_name]
    if collection.count_documents({"url": data["url"]}) == 0:
        collection.insert_one(data)
        st.write(f"[\u2713] Disimpan: {data['title']}")
        return True
    else:
        st.write(f"[=] Sudah ada: {data['title']}")
        return False

def load_articles_from_mongodb(db_name="artikel_db", collection_name="scraping"):
    client = MongoClient(MONGO_URI)
    db = client[db_name]
    collection = db[collection_name]
    return list(collection.find())

def crawl_article(url):
    try:
        response = requests.get(url, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        title = soup.find('h1').text if soup.find('h1') else 'No Title'
        paragraphs = soup.find_all('p')
        content = "\n".join([p.text for p in paragraphs])
        return {'url': url, 'title': title, 'content': content}
    except Exception as e:
        st.write(f"[ERROR] Gagal crawling artikel: {e}")
        return None

def crawl_kompasiana():
    st.write(f"\U0001F680 Crawling Kompasiana: {datetime.now()}")
    try:
        url = "https://www.kompasiana.com/tag/postur"
        response = requests.get(url)
        soup = BeautifulSoup(response.text, "html.parser")
        articles = soup.find_all("div", class_="timeline--item")

        for item in articles:
            content_div = item.find("div", class_="artikel--content")
            if content_div:
                a_tag = content_div.find("a")
                if a_tag and a_tag["href"]:
                    detail = crawl_article(a_tag["href"])
                    if detail:
                        save_to_mongodb(detail)
    except Exception as e:
        st.error(f"❌ Gagal crawl Kompasiana: {e}")

def crawl_detik():
    st.write(f"\U0001F680 Crawling Detik Health: {datetime.now()}")
    try:
        url = "https://health.detik.com/berita-detikhealth"
        response = requests.get(url)
        soup = BeautifulSoup(response.text, 'html.parser')
        articles = soup.find_all("article")

        for article in articles:
            a_tag = article.find("a")
            if a_tag and a_tag["href"]:
                detail = crawl_article(a_tag["href"])
                if detail:
                    save_to_mongodb(detail)
    except Exception as e:
        st.error(f"❌ Gagal crawl Detik Health: {e}")

def crawl_kompas():
    st.write(f"\U0001F680 Crawling Kompas Health: {datetime.now()}")
    try:
        url = "https://health.kompas.com"
        response = requests.get(url)
        soup = BeautifulSoup(response.text, 'html.parser')
        articles = soup.find_all("a", class_="article__link")

        for a_tag in articles:
            link = a_tag.get("href")
            if link and link.startswith("https://"):
                detail = crawl_article(link)
                if detail:
                    save_to_mongodb(detail)
    except Exception as e:
        st.error(f"❌ Gagal crawl Kompas Health: {e}")

def run_all_crawlers():
    crawl_kompasiana()
    crawl_detik()
    crawl_kompas()

def run_schedule():
    while True:
        schedule.run_pending()
        time.sleep(1)

def preprocess_text_list(text_list):
    factory = StopWordRemoverFactory()
    default_stopwords = factory.get_stop_words()
    stopword_list = set(default_stopwords + custom_stopwords)

    data_casefolding = pd.Series([text.lower() for text in text_list])
    filtering = data_casefolding.str.replace(r'[\W_]+', ' ', regex=True)
    data_tokens = [word_tokenize(line) for line in filtering]

    def stopword_filter(line):
        return [word for word in line if word not in stopword_list]

    data_stopremoved = [stopword_filter(tokens) for tokens in data_tokens]
    return data_stopremoved

# STREAMLIT UI
st.title("Auto Crawler + Analisis Artikel Kesehatan")
st.write("Crawling artikel dari berbagai sumber dan analisis kata yang sering muncul.")

st.sidebar.title("⚙ Pengaturan")
interval = st.sidebar.selectbox("⏱ Interval Crawling:", ["1 jam", "2 jam", "5 jam", "12 jam", "24 jam"])

if st.sidebar.button("Aktifkan Jadwal"):
    hours = int(interval.split()[0])
    schedule.every(hours).hours.do(run_all_crawlers)
    st.sidebar.success(f"Crawling dijadwalkan setiap {hours} jam.")
    threading.Thread(target=run_schedule, daemon=True).start()

if st.sidebar.button("Jalankan Sekarang"):
    run_all_crawlers()

st.header("Analisis Kata Paling Sering Muncul")
articles = load_articles_from_mongodb()
st.write(f"Total artikel di database: {len(articles)}")
contents = [a['content'] for a in articles if 'content' in a]

if contents:
    st.info("Melakukan preprocessing dan analisis...")
    processed_tokens_list = preprocess_text_list(contents)
    all_tokens = [token for tokens in processed_tokens_list for token in tokens]
    word_counts = Counter(all_tokens)
    top_words = word_counts.most_common(10)

    st.subheader("Top 10 Kata")
    st.write(top_words)

    st.subheader("Line Chart: Jumlah Artikel per Hari")
    dates = [a.get('timestamp', a.get('_id').generation_time).date() for a in articles]
    date_counts = pd.Series(dates).value_counts().sort_index()
    fig_date, ax_date = plt.subplots()
    date_counts.plot(ax=ax_date, kind='line', marker='o', color='blue')
    ax_date.set_title("Jumlah Artikel per Hari")
    ax_date.set_xlabel("Tanggal")
    ax_date.set_ylabel("Jumlah Artikel")
    ax_date.grid(True)
    st.pyplot(fig_date)

    st.subheader("Bar Chart: Top 10 Kata")
    fig_bar, ax_bar = plt.subplots(figsize=(10, 5))
    words, counts = zip(*top_words)
    ax_bar.bar(words, counts, color='green')
    ax_bar.set_title("Frekuensi 10 Kata Teratas")
    ax_bar.set_xlabel("Kata")
    ax_bar.set_ylabel("Frekuensi")
    plt.xticks(rotation=45)
    plt.tight_layout()
    st.pyplot(fig_bar)

    st.subheader("Word Cloud dari Seluruh Kata")
    wordcloud = WordCloud(width=800, height=400, background_color='white').generate_from_frequencies(word_counts)
    fig_wc, ax_wc = plt.subplots(figsize=(10, 5))
    ax_wc.imshow(wordcloud, interpolation='bilinear')
    ax_wc.axis('off')
    st.pyplot(fig_wc)

else:
    st.warning("Belum ada konten artikel yang tersedia untuk dianalisis.")
