import streamlit as st  # for UI
import socket           # help in networking
import os               # for file handling
import time             # time related functions
import threading        # to run background tasks (like file receiving)
from assets.twoway import *     # this file has send and receive file functions
from assets.console import *    # for live console display
import base64           # for bg image

# PAGE CONFIGURATION 
st.set_page_config(page_title='Modified UDP File Transfer', layout='centered')

# Background Image
def set_background_image(image_file):
    """Converts an image file to base64 and set it as the background."""
    with open(image_file, "rb") as image_file:
        encoded_string = base64.b64encode(image_file.read()).decode()
    
    html = f"""
    <style>
    .stApp {{
        background-image: url("data:image/png;base64,{encoded_string}");
        background-size: cover;
        background-repeat: no-repeat;
        background-attachment: fixed;
    }}
    </style>
    """
    st.markdown(html, unsafe_allow_html=True)

# Set background image, title and heading
set_background_image("assets/bg.jpg") 
st.title("FILE TRANSFER USING MODIFIED UDP PROTOCOL")
st.write("Send or receive file over local network using UDP with modified features!")

#MODE SELECTION 
mode =st.radio('Select Mode:',['SEND FILE','RECEIVE FILE'])

#Placeholders for each mode 
# ----------------------- SENDER MODE ------------------------
if mode=='SEND FILE':
    st.subheader('Send A File')

    #1.getting dest_ip and optional port number as inputs
    st.write("##### Destination Details")
    dest_ip=st.text_input('Enter the Destination IP address:').strip()
    port=st.number_input('Enter the Port No (default is 9999)',value=9999,step=1,format='%d')

    # transfer features inputs to modify settings
    st.write("##### Transfer Features")
    timeout=st.number_input('Enter the timeout (default is 2 sec)',value=2, min_value=1, max_value=10)
    maxtries=st.number_input('Enter max. tries (default is 5 tries)',value=5, min_value=1, max_value=10)
    # packet size (default = 8000 bytes), larger packets for faster networks
    packet_size = st.selectbox('Select packet size (in bytes)', options=[1024,2048,4096,8000], index=3) 
    # window size (default = 4, behaves like Stop-and-Wait if set to 1), sends multiple packets to increase efficiency
    window_size = st.number_input('Enter window size (packet per ack, set to 1 for Stop-and-Wait)',value=4, min_value=1, max_value=10)
    logging = st.checkbox('Enable Logging on Console', value=False)
    
    #2.upload a file using streamlit file uploader
    st.write("##### Select File")
    uploaded_file=st.file_uploader("Select a file to send",type=None)

    #3.adding a send button
    if st.button("Send File"):
        if not dest_ip:
            st.error('Please enter the receiver IP address!')
        elif not uploaded_file:
            st.error("Please first upload a file to send!")
        else:
            #4.saving the uploaded file temporary
            temp_path=os.path.join(".",uploaded_file.name)
            with open(temp_path,'wb') as f:
                f.write(uploaded_file.getbuffer())
            
            #now show a status message while sending 
            with st.spinner(f'sending {uploaded_file.name} to {dest_ip}:{port}...'):
                try:
                    # call the live console if logging is enabled
                    update_log, clear_log = create_live_console(height=200)

                    #updates log messages
                    def log_callback(msg):
                        update_log(msg)

                    #6.calling the sendfile() func
                    send_file(dest_ip, temp_path, port_no=port, timeout=timeout, max_retries=maxtries,
                              packet_size=packet_size, window_size=window_size, enable_log=logging, 
                              log_callback=log_callback)
                    st.success('FILE SUCCESSFULLY SENT')
                except Exception as e:
                    print(f'ERROR:{e}')
                finally:
                    #remove the temp file
                    os.remove(temp_path)
    

# ----------------------- RECEIVER MODE ------------------------
elif mode=='RECEIVE FILE':
    st.subheader('Receive A File')

    # 1. Take port number input
    port = st.number_input("Enter the port number to listen (default is 9999)",value=9999)

    # 2. let user choose where to save the file
    savedir = st.text_input("Enter path to save received file (default is current directory)",value=".")

    # logging choice
    logging = st.checkbox('Enable Logging on Console', value=False)
    
    # 3. Start receiving when button is clicked
    if st.button("Start Receiving"):
        try:
            update_log, clear_log = create_live_console(height=200)
            receive_file(port=port, save_dir=savedir, enable_log=logging, log_callback=update_log)

            # 5.Success message after completion
            st.success("File received successfully!")

        except Exception as e:
            st.error(f"ERROR:{e}")
              
