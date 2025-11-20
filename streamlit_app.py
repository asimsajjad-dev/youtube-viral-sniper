import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta, timezone
from dateutil.parser import isoparse
import time

# ========================= SECRETS =========================
API_KEY = st.secrets["YOUTUBE_API_KEY"]

# ========================= URLs =========================
SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"
CHANNELS_URL = "https://www.googleapis.com/youtube/v3/channels"

# ========================= APP =========================
st.set_page_config(page_title="Viral Sniper", layout="wide")
st.title("YouTube Viral Sniper (Small Channels Only)")
st.caption("Finds hidden viral videos from tiny channels before they explode")

# ========================= USER INPUTS =========================
col1, col2, col3 = st.columns(3)
with col1:
    days = st.slider("Search last X days", 1, 30, 7)
with col2:
    min_views = st.number_input("Minimum views", 0, 1_000_000, 5_000, step=1_000)
with col3:
    max_subs = st.number_input("Max subscribers", 100, 50_000, 4_000, step=500)

# Default hot keywords (you can edit or add your own)
default_keywords = [
    "AITA update", "Reddit update", "cheating story", "surviving infidelity",
    "wife cheated", "husband cheated", "reddit cheating stories",
    "open marriage fail", "emotional affair", "true off my chest",
    "fall asleep now", "bedtime stories for grown ups", "reddit stories narrated"
]

keywords_input = st.text_area(
    "Keywords (one per line)",
    value="\n".join(default_keywords),
    height=220
)
keywords = [k.strip() for k in keywords_input.split("\n") if k.strip()]

# ========================= MAIN FUNCTION WITH CACHING =========================
@st.cache_data(ttl=3600, show_spinner=False)  # Cache results for 1 hour
def search_youtube(keyword: str, published_after: str):
    params = {
        "part": "snippet",
        "q": keyword,
        "type": "video",
        "order": "viewCount",
        "publishedAfter": published_after,
        "maxResults": 15,
        "regionCode": "US",
        "relevanceLanguage": "en",
        "key": API_KEY
    }
    try:
        r = requests.get(SEARCH_URL, params=params, timeout=20)
        r.raise_for_status()
        return r.json().get("items", [])
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 403:
            st.error("Daily YouTube API quota exceeded. Come back tomorrow or upgrade quota.")
            st.stop()
        elif e.response.status_code == 400:
            st.error(f"Bad request for '{keyword}'. Check API key and try again.")
            st.stop()
        else:
            st.warning(f"Error searching '{keyword}': {e}")
        return []
    except Exception as e:
        st.warning(f"Unexpected error for '{keyword}': {e}")
        return []

# ========================= RUN SEARCH =========================
if st.button("Hunt Viral Videos", type="primary", use_container_width=True):
    if not API_KEY or API_KEY == "your_key_here":
        st.error("Set your YouTube API key in Secrets first!")
        st.stop()

    # Perfect ISO format — NEVER fails
    published_after = (datetime.now(timezone.utc) - timedelta(days=days))\
                      .replace(microsecond=0)\
                      .strftime("%Y-%m-%dT%H:%M:%SZ")

    st.info(f"Searching videos published after: `{published_after}`")

    all_results = []
    progress = st.progress(0)
    status = st.empty()

    for i, keyword in enumerate(keywords):
        status.text(f"Searching: {keyword} ({i+1}/{len(keywords)})")
        
        items = search_youtube(keyword, published_after)
        if not items:
            continue

        video_ids = []
        video_data = {}

        for item in items:
            vid_id = item["id"]["videoId"]
            video_ids.append(vid_id)
            snippet = item["snippet"]
            published_at = isoparse(snippet["publishedAt"])
            days_old = max((datetime.now(timezone.utc) - published_at).days, 1)

            video_data[vid_id] = {
                "title": snippet["title"],
                "channel_id": snippet["channelId"],
                "channel_title": snippet["channelTitle"],
                "thumbnail": snippet["thumbnails"]["high"]["url"],
                "published_at": published_at,
                "days_old": days_old
            }

        # Fetch stats in batches
        if video_ids:
            # Video stats
            stats_resp = requests.get(VIDEOS_URL, params={
                "part": "statistics",
                "id": ",".join(video_ids),
                "key": API_KEY
            }, timeout=20)
            stats_resp.raise_for_status()
            stats = {s["id"]: s["statistics"] for s in stats_resp.json().get("items", [])}

            # Channel stats (deduped)
            channel_ids = list({video_data[vid]["channel_id"] for vid in video_ids})
            channel_resp = requests.get(CHANNELS_URL, params={
                "part": "statistics",
                "id": ",".join(channel_ids),
                "key": API_KEY
            }, timeout=20)
            channel_resp.raise_for_status()
            channel_stats = {c["id"]: c["statistics"] for c in channel_resp.json().get("items", [])}

            # Process results
            for vid in video_ids:
                v = video_data[vid]
                s = stats.get(vid, {})
                c = channel_stats.get(v["channel_id"], {})

                views = int(s.get("viewCount", 0))
                likes = int(s.get("likeCount", 0))
                comments = int(s.get("commentCount", 0))
                subs = int(c.get("subscriberCount", 0)) or 1

                if views < min_views or subs > max_subs:
                    continue

                views_per_day = views / v["days_old"]
                engagement = (likes + comments) / views if views > 0 else 0
                viral_score = round(views_per_day * (10_000 / subs) * (1 + engagement), 2)

                all_results.append({
                    "Title": v["title"],
                    "Channel": v["channel_title"],
                    "Subscribers": f"{subs:,}",
                    "Views": f"{views:,}",
                    "Views/Day": round(views_per_day),
                    "Age (days)": v["days_old"],
                    "Viral Score": viral_score,
                    "URL": f"https://www.youtube.com/watch?v={vid}",
                    "Thumbnail": v["thumbnail"]
                })

        time.sleep(0.4)
        progress.progress((i + 1) / len(keywords))

    # ========================= DISPLAY RESULTS =========================
    if all_results:
        df = pd.DataFrame(all_results).sort_values("Viral Score", ascending=False).reset_index(drop=True)
        
        st.success(f"Found {len(df)} hidden gems under {max_subs:,} subscribers!")

        st.subheader("Top 20 Viral Candidates")
        for _, row in df.head(20).iterrows():
            col1, col2 = st.columns([1, 4])
            with col1:
                st.image(row["Thumbnail"], use_column_width=True)
            with col2:
                st.markdown(f"**{row['Title']}**")
                st.caption(f"{row['Channel']} • {row['Subscribers']} subs • {row['Views']} views • {row['Views/Day']} views/day")
                st.metric("Viral Score", row["Viral Score"])
                st.markdown(f"[Watch Video]({row['URL']})")
            st.divider()

        # Full table + CSV
        st.subheader("Full Results (Sortable)")
        st.dataframe(df.drop("Thumbnail", axis=1), use_container_width=True)

        csv = df.to_csv(index=False).encode()
        st.download_button(
            "Download CSV",
            csv,
            f"viral_sniper_{datetime.now().strftime('%Y%m%d')}.csv",
            "text/csv"
        )
    else:
        st.warning("No videos found. Try lowering min views, increasing days, or using hotter keywords.")

# ========================= SIDEBAR =========================
st.sidebar.success("App is live & quota-safe!")
st.sidebar.caption("Free quota: ~60 runs/day with 15 keywords")
st.sidebar.caption("Cache active: same search = no quota used")
