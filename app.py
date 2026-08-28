import streamlit as st
import os
import tempfile
import json
import requests
from openai import OpenAI
from moviepy.editor import VideoFileClip, concatenate_videoclips, AudioFileClip, CompositeAudioClip

# Streamlit UI Configuration
st.set_page_config(page_title="AI Video Recap Generator", page_icon="🎬", layout="wide")
st.title("🎬 AI Video Recap Generator")
st.write("ဗီဒီယို တင်လိုက်ရုံဖြင့် အလိုအလျောက် Recap ဖြတ်ပေးပြီး Voiceover ထည့်သွင်းပေးမည့် Web App")

# Sidebar for API Keys & Options
st.sidebar.header("🔑 API Configurations")
openai_key = st.sidebar.text_input("OpenAI API Key", type="password")
elevenlabs_key = st.sidebar.text_input("ElevenLabs API Key (Optional)", type="password")
voice_id = st.sidebar.text_input("ElevenLabs Voice ID", value="21m00Tcm4TlvDq8ikWAM")  # Default Voice (Rachel)

st.sidebar.header("⚙️ Editing Settings")
target_duration = st.sidebar.slider("Target Recap Duration (Seconds)", min_value=15, max_value=90, value=30)
keep_original_audio = st.sidebar.checkbox("Original Audio နောက်ခံသံ ပါဝင်စေမည် (15% Volume)", value=True)

# Main File Uploader
uploaded_file = st.file_uploader("ဗီဒီယိုဖိုင် တင်ပါ (MP4, MOV, AVI)", type=["mp4", "mov", "avi"])

def extract_audio(video_path, audio_out_path):
    clip = VideoFileClip(video_path)
    clip.audio.write_audiofile(audio_out_path, verbose=False, logger=None)
    clip.close()

def transcribe_audio_whisper(client, audio_path):
    with open(audio_path, "rb") as audio_file:
        response = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            response_format="verbose_json",
            timestamp_granularities=["segment"]
        )
    return response.segments

def select_highlights_and_script(client, transcript_segments, duration_limit):
    prompt = f"""
    You are an expert video editor and storyteller.
    Below is a transcript of a video with start/end timestamps.
    
    Task:
    1. Select the most engaging highlights that form a cohesive narrative. Total combined duration of highlights should be roughly {duration_limit} seconds.
    2. Write a concise, natural Burmese recap narration script based ONLY on the context of the selected highlights.
    
    Transcript:
    {json.dumps(transcript_segments, indent=2)}
    
    Return ONLY a valid JSON object matching this exact format:
    {{
        "highlights": [
            {{"start": 0.0, "end": 5.2}},
            {{"start": 12.5, "end": 18.0}}
        ],
        "recap_script_burmese": "ဒီနေရာမှာ အနှစ်ချုပ် ဇာတ်ကြောင်းပြော ရေးပါ..."
    }}
    """
    
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"}
    )
    return json.loads(response.choices[0].message.content)

def generate_voiceover_elevenlabs(api_key, text, voice_id, output_path):
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": api_key
    }
    data = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}
    }
    res = requests.post(url, json=data, headers=headers)
    if res.status_code == 200:
        with open(output_path, "wb") as f:
            f.write(res.content)
        return True
    return False

def generate_voiceover_openai(client, text, output_path):
    response = client.audio.speech.create(
        model="tts-1",
        voice="alloy",
        input=text
    )
    response.stream_to_file(output_path)
    return True

if uploaded_file is not None:
    st.video(uploaded_file)
    
    if st.button("🚀 Start Recap Workflow", type="primary"):
        if not openai_key:
            st.error("❌ ကျေးဇူးပြု၍ OpenAI API Key ထည့်သွင်းပေးပါ။")
        else:
            client = OpenAI(api_key=openai_key)
            
            with tempfile.TemporaryDirectory() as temp_dir:
                # File Paths
                input_video_path = os.path.join(temp_dir, "input.mp4")
                extracted_audio_path = os.path.join(temp_dir, "temp_audio.mp3")
                voiceover_path = os.path.join(temp_dir, "voiceover.mp3")
                output_video_path = os.path.join(temp_dir, "recap_output.mp4")
                
                # Save uploaded file to temp
                with open(input_video_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())
                
                # Step 1: Extract Audio
                with st.spinner("🔊 Step 1/5: Extracting audio from video..."):
                    extract_audio(input_video_path, extracted_audio_path)
                
                # Step 2: Speech to Text (Whisper)
                with st.spinner("📝 Step 2/5: Transcribing speech with Whisper..."):
                    segments = transcribe_audio_whisper(client, extracted_audio_path)
                    simplified_segments = [{"start": s['start'], "end": s['end'], "text": s['text']} for s in segments]
                
                # Step 3: Highlight Selection & Scripting (GPT-4o)
                with st.spinner("🧠 Step 3/5: AI is choosing top highlights & writing script..."):
                    ai_result = select_highlights_and_script(client, simplified_segments, target_duration)
                    highlights = ai_result.get("highlights", [])
                    recap_script = ai_result.get("recap_script_burmese", "")
                
                st.info(f"📜 **Generated Voiceover Script (Burmese):**\n{recap_script}")
                
                # Step 4: AI Voiceover Generation
                with st.spinner("🎙️ Step 4/5: Generating AI Voiceover..."):
                    if elevenlabs_key:
                        success = generate_voiceover_elevenlabs(elevenlabs_key, recap_script, voice_id, voiceover_path)
                        if not success:
                            st.warning("ElevenLabs Voiceover မအောင်မြင်ပါ၊ OpenAI TTS ဖြင့် အစားထိုး ထုတ်ပေးပါမည်။")
                            generate_voiceover_openai(client, recap_script, voiceover_path)
                    else:
                        generate_voiceover_openai(client, recap_script, voiceover_path)
                
                # Step 5: Render Video Editing
                with st.spinner("✂️ Step 5/5: Cutting highlights and rendering video..."):
                    full_video = VideoFileClip(input_video_path)
                    clips = []
                    for h in highlights:
                        start, end = h["start"], h["end"]
                        if start < full_video.duration:
                            end = min(end, full_video.duration)
                            clips.append(full_video.subclip(start, end))
                    
                    if clips:
                        final_clip = concatenate_videoclips(clips)
                        narration_audio = AudioFileClip(voiceover_path)
                        
                        if keep_original_audio and final_clip.audio:
                            bg_audio = final_clip.audio.volumex(0.15)
                            mixed_audio = CompositeAudioClip([bg_audio, narration_audio])
                            final_clip = final_clip.set_audio(mixed_audio)
                        else:
                            final_clip = final_clip.set_audio(narration_audio)
                        
                        final_clip.write_videofile(
                            output_video_path,
                            codec="libx264",
                            audio_codec="aac",
                            verbose=False,
                            logger=None
                        )
                        
                        full_video.close()
                        final_clip.close()
                        
                        st.success("✅ Recap Video ပြုလုပ်ပြီးပါပြီ!")
                        st.video(output_video_path)
                        
                        with open(output_video_path, "rb") as v_file:
                            st.download_button(
                                label="📥 Recap Video ဒေါင်းလုဒ်ဆွဲမည်",
                                data=v_file,
                                file_name="recap_final.mp4",
                                mime="video/mp4"
                            )
                    else:
                        st.error("Highlight မထုတ်ယူနိုင်ပါ။ ဗီဒီယိုအား အသစ်ပြန်လည် စမ်းသပ်ပေးပါ။")
