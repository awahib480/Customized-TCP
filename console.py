import streamlit as st
import time

def create_live_console(height=200, bg_color="#111", text_color="#0f0"):
    """
    Creates a live-updating console in Streamlit using st.empty().
    Returns two things:
      1. update_log(msg): function to append and update messages live
      2. clear_log(): function to clear the console (optional)
    """

    log_container = st.empty()   # placeholder for log display
    logs = []                    # list to keep messages

    def update_log(msg):
        """Appends a new log message and updates the console."""
        logs.append(msg)
        html = (
            f"<div style='height:{height}px; overflow-y:auto; background-color:{bg_color}; "
            f"color:{text_color}; padding:8px; font-family:monospace; border-radius:5px;'>"
            + "<br>".join(logs)
            + "</div>"
        )
        log_container.markdown(html, unsafe_allow_html=True)

    def clear_log():
        """Clears all log messages from console."""
        logs.clear()
        log_container.empty()

    return update_log, clear_log