import streamlit as st
import requests
from datetime import datetime, timedelta
import pandas as pd
from dateutil.parser import isoparse
import time

# === SECURITY FIRST ===
API_KEY = st.secrets["YOUTUBE_API_KEY"]

YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
YOUTUBE_VIDEO_URL = "https://www.googleapis.com/youtube/v3/videos"
YOUTUBE_CHANNEL_URL = "https://www.googleapis.com/youtube/v3/channels"

st.set_page_config(page_title="Viral Reddit Stories Sniper", layout="wide")
st.title("🔥 YouTube Viral Reddit/Drama Stories Sniper (Small Channels Only)")

# === USER CONTROLS ===
col1, col2, col3 = st.columns(3)
with col1:
    days = st.slider("Search last X days", 1, 30, 7)
with col2:
    min_views = st.number_input("Minimum views on video", 0, 500000, 10000)
with col3:
    max_subs = st.number_input("Max subscribers", 100, 10000, 3000)

default_keywords = [
    "AITA update", "Reddit update", "cheating story", "surviving infidelity", 
    "open marriage fail", "wife cheated", "husband cheated", "reddit cheating stories",
    "exposed cheater", "emotional affair", "reddit relationship advice", "true off my chest",
    "reddit stories", "aita", "relationship_advice", "infidelity", "boruto two blue vortex"
]

custom_keywords = st.text_area("Custom keywords (one per line)", 
    value="\n".join(default_keywords), height=200)
keywords = [k.strip() for k in custom_keywords.split("\n") if k.strip()]

if st.button("🚀 Hunt Viral Videos", type="primary"):
    if not API_KEY:
        st.error("Set your YouTube API key in Secrets first!")
        st.stop()

    start_date = (datetime.utcnow() - timedelta(days=days)).isoformat("T") + "Z"
    all_results = []
    progress_bar = st.progress(0)
    status_text = st.empty()

    for idx, keyword in enumerate(keywords):
        status_text.text(f"Searching: {keyword} ({idx+1}/{len(keywords)})")
        
        search_params = {
            "part": "snippet",
            "q": keyword,
            "type": "video",
            "order": "viewCount",
            "publishedAfter": start_date,
            "maxResults": 10,
            "regionCode": "US",
            "relevanceLanguage": "en",
            "key": API_KEY,
        }

        try:
            response = requests.get(YOUTUBE_SEARCH_URL, params=search_params, timeout=10)
            response.raise_for_status()
            data = response.json()

            if not data.get("items"):
                continue

            videos = data["items"]
            video_details = []
            video_ids = []

            for video in videos:
                vid_id = video["id"]["videoId"]
                published_at = isoparse(video["snippet"]["publishedAt"])
                days_old = max((datetime.utcnow() - published_at).days, 1)

                video_details.append({
                    "video_id": vid_id,
                    "title": video["snippet"]["title"],
                    "channel_id": video["snippet"]["channelId"],
                    "channel_title": video["snippet"]["channelTitle"],
                    "published_at": published_at,
                    "days_old": days_old,
                    "thumbnail": video["snippet"]["thumbnails"]["high"]["url"]
                })
                video_ids.append(vid_id)

            # Video stats
            stats_response = requests.get(YOUTUBE_VIDEO_URL, params={
                "part": "statistics,contentDetails",
                "id": ",".join(video_ids),
                "key": API_KEY
            }, timeout=10)
            stats_response.raise_for_status()
            stats_data = stats_response.json()

            # Channel stats (deduped)
            unique_channel_ids = list({v["channel_id"] for v in video_details})
            channel_response = requests.get(YOUTUBE_CHANNEL_URL, params={
                "part": "statistics",
                "id": ",".join(unique_channel_ids),
                "key": API_KEY
            }, timeout=10)
            channel_response.raise_for_status()
            channel_data = channel_response.json()

            channel_stats = {item["id"]: item["statistics"] for item in channel_data.get("items", [])}

            # Process results
            for video in video_details:
                vid_stats = next((s["statistics"] for s in stats_data["items"] if s["id"] == video["video_id"]), {})
                chan_stats = channel_stats.get(video["channel_id"], {})

                views = int(vid_stats.get("viewCount", 0))
                likes = int(vid_stats.get("likeCount", 0))
                comments = int(vid_stats.get("commentCount", 0))
                subs = int(chan_stats.get("subscriberCount", 0)) or 0

                if views < min_views or subs > max_subs or subs == 0:
                    continue

                views_per_day = views / video["days_old"]
                engagement_rate = (likes + comments) / views if views > 0 else 0
                viral_score = round(views_per_day * (10000 / (subs + 1000)) * (1 + engagement_rate), 1)

                all_results.append({
                    "Title": video["title"],
                    "Channel": video["channel_title"],
                    "Subs": f"{subs:,}",
                    "Views": f"{views:,}",
                    "Likes": likes,
                    "Comments": comments,
                    "Age (days)": video["days_old"],
                    "Views/Day": round(views_per_day, 1),
                    "Engagement %": round(engagement_rate * 100, 2),
                    "Viral Score": viral_score,
                    "URL": f"https://www.youtube.com/watch?v={video['video_id']}",
                    "Thumbnail": video["thumbnail"]
                })

            time.sleep(0.25)  # Polite to API

        except Exception as e:
            st.warning(f"Error with '{keyword}': {e}")
            continue

        progress_bar.progress((idx + 1) / len(keywords))

    # === DISPLAY ===
    if all_results:
        df = pd.DataFrame(all_results)
        df = df.sort_values("Viral Score", ascending=False).reset_index(drop=True)
        
        st.success(f"🚀 Found {len(df)} potential viral videos under {max_subs:,} subs!")
        
        st.subheader("🏆 Top 15 Hidden Gems")
        for _, row in df.head(15).iterrows():
            c1, c2 = st.columns([1, 4])
            with c1:
                st.image(row["Thumbnail"], use_column_width=True)
            with c2:
                st.markdown(f"**{row['Title']}**")
                st.write(f"Channel: {row['Channel']} • {row['Subs']} subs • {row['Views']} views")
                st.write(f"Views/day: {row['Views/Day']} • Viral Score: **{row['Viral Score']}**")
                st.markdown(f"[Watch on YouTube]({row['URL']})")
            st.divider()

        st.subheader("Full Table (Sortable)")
        st.dataframe(df.drop("Thumbnail", axis=1), use_container_width=True)

        csv = df.to_csv(index=False).encode()
        st.download_button("📥 Download CSV", csv, "viral_gems_nov2025.csv", "text/csv")

    else:
        st.warning("No videos matched your filters. Try lowering min views or increasing days.")
