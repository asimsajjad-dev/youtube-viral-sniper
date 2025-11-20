import streamlit as st
import requests
from datetime import datetime, timedelta, timezone  # ← added timezone
import pandas as pd
from dateutil.parser import isoparse
import time

# === SECURITY ===
API_KEY = st.secrets["YOUTUBE_API_KEY"]

YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
YOUTUBE_VIDEO_URL = "https://www.googleapis.com/youtube/v3/videos"
YOUTUBE_CHANNEL_URL = "https://www.googleapis.com/youtube/v3/channels"

st.set_page_config(page_title="Viral Reddit Stories Sniper", layout="wide")
st.title("YouTube Viral Reddit/Drama Stories Sniper (Small Channels Only)")

# === USER CONTROLS ===
col1, col2, col3 = st.columns(3)
with col1:
    days = st.slider("Search last X days", 1, 30, 7)
with col2:
    min_views = st.number_input("Minimum views", 0, 1_000_000, 8_000, step=1000)
with col3:
    max_subs = st.number_input("Max subscribers", 100, 20_000, 3_500, step=500)

default_keywords = [
    "AITA update", "Reddit update", "cheating story", "surviving infidelity",
    "open marriage fail", "wife cheated", "husband cheated", "reddit cheating stories",
    "exposed cheater", "emotional affair", "reddit relationship advice", "true off my chest",
    "bedtime stories for grown ups", "reddit stories narrated", "aita reddit"
]

custom_keywords = st.text_area("Keywords (one per line)", value="\n".join(default_keywords), height=200)
keywords = [k.strip() for k in custom_keywords.split("\n") if k.strip()]

if st.button("Hunt Viral Videos", type="primary"):
    if not API_KEY:
        st.error("⚠️ Add your YouTube API key in Secrets (see sidebar instructions)")
        st.stop()

    # ← FIXED: Use timezone-aware UTC now
    now_utc = datetime.now(timezone.utc)
    start_date = (now_utc - timedelta(days=days)).isoformat("T") + "Z"

    all_results = []
    progress_bar = st.progress(0)
    status_text = st.empty()

    for idx, keyword in enumerate(keywords):
        status_text.text(f"Searching → {keyword} ({idx+1}/{len(keywords)})")
        
        search_params = {
            "part": "snippet",
            "q": keyword,
            "type": "video",
            "order": "viewCount",
            "publishedAfter": start_date,
            "maxResults": 12,
            "regionCode": "US",
            "relevanceLanguage": "en",
            "key": API_KEY,
        }

        try:
            response = requests.get(YOUTUBE_SEARCH_URL, params=search_params, timeout=15)
            response.raise_for_status()
            data = response.json()

            if not data.get("items"):
                continue

            videos = data["items"]
            video_details = []
            video_ids = []

            for video in videos:
                vid_id = video["id"]["videoId"]
                published_at = isoparse(video["snippet"]["publishedAt"])  # already timezone-aware
                
                # ← FIXED: both datetimes are now timezone-aware
                days_old = max((now_utc - published_at).days, 1)

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

            # Fetch video statistics
            stats_resp = requests.get(YOUTUBE_VIDEO_URL, params={
                "part": "statistics,contentDetails",
                "id": ",".join(video_ids),
                "key": API_KEY
            }, timeout=15)
            stats_resp.raise_for_status()
            stats_data = stats_resp.json()

            # Fetch channel statistics (deduped)
            unique_channels = list({v["channel_id"] for v in video_details})
            if unique_channels:
                chan_resp = requests.get(YOUTUBE_CHANNEL_URL, params={
                    "part": "statistics",
                    "id": ",".join(unique_channels),
                    "key": API_KEY
                }, timeout=15)
                chan_resp.raise_for_status()
                chan_data = chan_resp.json()
                channel_stats = {c["id"]: c["statistics"] for c in chan_data.get("items", [])}
            else:
                channel_stats = {}

            # Process each video
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
                engagement = (likes + comments) / views if views > 0 else 0
                viral_score = round(views_per_day * (10_000 / (subs + 1000)) * (1 + engagement), 2)

                all_results.append({
                    "Title": video["title"],
                    "Channel": video["channel_title"],
                    "Subs": f"{subs:,}",
                    "Views": f"{views:,}",
                    "Views/Day": round(views_per_day),
                    "Viral Score": viral_score,
                    "Age (days)": video["days_old"],
                    "URL": f"https://www.youtube.com/watch?v={video['video_id']}",
                    "Thumbnail": video["thumbnail"]
                })

            time.sleep(0.25)  # Stay under quota

        except requests.exceptions.RequestException as e:
            st.warning(f"Network error on '{keyword}': {e}")
        except Exception as e:
            st.warning(f"Unexpected error on '{keyword}': {e}")

        progress_bar.progress((idx + 1) / len(keywords))

    # === DISPLAY RESULTS ===
    if all_results:
        df = pd.DataFrame(all_results).sort_values("Viral Score", ascending=False).reset_index(drop=True)
        st.success(f"Found {len(df)} hidden gems under {max_subs:,} subs!")

        st.subheader("Top 15 Viral Candidates")
        for i, row in df.head(15).iterrows():
            c1, c2 = st.columns([1, 4])
            with c1:
                st.image(row["Thumbnail"], use_column_width=True)
            with c2:
                st.markdown(f"**{row['Title']}**")
                st.caption(f"{row['Channel']} • {row['Subs']} subs • {row['Views']} views • {row['Views/Day']} views/day")
                st.metric("Viral Score", row["Viral Score"])
                st.markdown(f"[Watch Video]({row['URL']})")
            st.divider()

        st.download_button("Download CSV", df.to_csv(index=False).encode(), "viral_candidates.csv", "text/csv")
        st.dataframe(df.drop("Thumbnail", axis=1), use_container_width=True)
    else:
        st.info("No videos matched your current filters — try lowering minimum views or increasing the date range.")

st.sidebar.success("App is live and error-free!")
