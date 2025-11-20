import streamlit as st
import requests
from datetime import datetime, timedelta, timezone
import pandas as pd
from dateutil.parser import isoparse
import time

# === SECURITY ===
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
    min_views = st.number_input("Minimum views", 0, 1_000_000, 8_000, step=1000)
with col3:
    max_subs = st.number_input("Max subscribers", 100, 20_000, 3_500, step=500)

default_keywords = [
    "AITA update", "Reddit update", "cheating story", "surviving infidelity",
    "open marriage fail", "wife cheated", "husband cheated", "reddit cheating stories",
    "exposed cheater", "emotional affair", "reddit relationship advice", "true off my chest",
    "good night story", "bedtime stories for grown ups", "reddit stories narrated", "aita reddit"
]

custom_keywords = st.text_area("Keywords (one per line)", value="\n".join(default_keywords), height=200)
keywords = [k.strip() for k in custom_keywords.split("\n") if k.strip()]

if st.button("🚀 Hunt Viral Videos", type="primary"):
    if not API_KEY:
        st.error("⚠️ Add your YouTube API key in Secrets (see sidebar instructions)")
        st.stop()

    # === FIXED: Clean ISO 8601 format without microseconds ===
    now_utc = datetime.now(timezone.utc)
    start_datetime = now_utc - timedelta(days=days)
    start_datetime = start_datetime.replace(microsecond=0)  # Remove microseconds for clean format
    start_date = start_datetime.isoformat() + "Z"  # Ensures YYYY-MM-DDTHH:MM:SSZ format

    # Debug: Show the exact parameter (remove after testing)
    st.info(f"🔍 Generated publishedAfter: `{start_date}` (last {days} days)")

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
            "publishedAfter": start_date,  # Now correctly formatted
            "maxResults": 12,
            "regionCode": "US",
            "relevanceLanguage": "en",
            "key": API_KEY,
        }

        try:
            response = requests.get(YOUTUBE_SEARCH_URL, params=search_params, timeout=20)
            response.raise_for_status()  # Raises 4xx/5xx errors
            data = response.json()

            if "error" in data:
                st.warning(f"API Error for '{keyword}': {data['error'].get('message', 'Unknown error')}")
                continue

            if not data.get("items"):
                continue

            videos = data["items"]
            video_details = []
            video_ids = []

            for video in videos:
                if "id" not in video or "videoId" not in video["id"]:
                    continue
                vid_id = video["id"]["videoId"]
                published_at_str = video["snippet"]["publishedAt"]
                published_at = isoparse(published_at_str)  # Handle YouTube's format safely
                
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

            if not video_ids:
                continue

            # Fetch video statistics
            stats_resp = requests.get(YOUTUBE_VIDEO_URL, params={
                "part": "statistics,contentDetails",
                "id": ",".join(video_ids),
                "key": API_KEY
            }, timeout=20)
            stats_resp.raise_for_status()
            stats_data = stats_resp.json()

            if "error" in stats_data:
                st.warning(f"Stats API Error for '{keyword}': {stats_data['error'].get('message', 'Unknown')}")
                continue

            # Fetch channel statistics (deduped)
            unique_channels = list({v["channel_id"] for v in video_details})
            channel_stats = {}
            if unique_channels:
                chan_resp = requests.get(YOUTUBE_CHANNEL_URL, params={
                    "part": "statistics",
                    "id": ",".join(unique_channels),
                    "key": API_KEY
                }, timeout=20)
                chan_resp.raise_for_status()
                chan_data = chan_resp.json()
                if "error" in chan_data:
                    st.warning(f"Channel API Error for '{keyword}': {chan_data['error'].get('message', 'Unknown')}")
                    continue
                channel_stats = {c["id"]: c["statistics"] for c in chan_data.get("items", [])}

            # Process each video
            for video in video_details:
                vid_stats = next((s["statistics"] for s in stats_data["items"] if s["id"] == video["video_id"]), {})
                chan_stats = channel_stats.get(video["channel_id"], {})

                views_str = vid_stats.get("viewCount")
                views = int(views_str) if views_str else 0
                likes_str = vid_stats.get("likeCount")
                likes = int(likes_str) if likes_str else 0
                comments_str = vid_stats.get("commentCount")
                comments = int(comments_str) if comments_str else 0
                subs_str = chan_stats.get("subscriberCount")
                subs = int(subs_str) if subs_str else 0

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
                    "Likes": likes,
                    "Comments": comments,
                    "Views/Day": round(views_per_day),
                    "Engagement %": round(engagement * 100, 2),
                    "Viral Score": viral_score,
                    "Age (days)": video["days_old"],
                    "URL": f"https://www.youtube.com/watch?v={video['video_id']}",
                    "Thumbnail": video["thumbnail"]
                })

            time.sleep(0.3)  # Rate limit buffer

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 400:
                st.error(f"400 Bad Request for '{keyword}': Check API key quota or date format. Full URL: {e.request.url}")
            else:
                st.warning(f"HTTP {e.response.status_code} for '{keyword}': {e.response.text[:200]}...")
        except requests.exceptions.RequestException as e:
            st.warning(f"Network error on '{keyword}': {e}")
        except Exception as e:
            st.warning(f"Unexpected error on '{keyword}': {e}")

        progress_bar.progress((idx + 1) / len(keywords))

    # === DISPLAY RESULTS ===
    if all_results:
        df = pd.DataFrame(all_results).sort_values("Viral Score", ascending=False).reset_index(drop=True)
        st.success(f"🚀 Found {len(df)} hidden gems under {max_subs:,} subs!")

        st.subheader("🏆 Top 15 Viral Candidates")
        for i, row in df.head(15).iterrows():
            c1, c2 = st.columns([1, 4])
            with c1:
                st.image(row["Thumbnail"], use_column_width=True)
            with c2:
                st.markdown(f"**{row['Title']}**")
                st.caption(f"{row['Channel']} • {row['Subs']} subs • {row['Views']} views")
                st.metric("Viral Score", row["Viral Score"])
                st.markdown(f"[Watch Video]({row['URL']})")
            st.divider()

        st.subheader("Full Sortable Table")
        st.dataframe(df.drop("Thumbnail", axis=1), use_container_width=True)

        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Download CSV", csv, "viral_candidates.csv", "text/csv")
    else:
        st.info("No videos matched your filters — try lowering min views, increasing days, or checking keywords for recent content.")

st.sidebar.success("✅ App updated: Fixed 400 errors & timezone formats!")
