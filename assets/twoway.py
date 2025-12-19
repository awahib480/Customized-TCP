import socket 
import os 

# ---------------------------------------------------------------------
# --------------------- MAKING SEND FILE FUNCTION ---------------------
# ---------------------------------------------------------------------
def send_file(dest_ip, filepath, timeout=2, port_no=9999, max_retries=5, packet_size=8000, window_size=4, enable_log=False, log_callback=None):
    # Log function
    def log(msg):
        if enable_log:
            if log_callback:
                log_callback(msg)
            else:
                print(msg)
    
    log(f"Initializing connection to {dest_ip}:{port_no}...")   # Log message

    clientsocket=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)  # (IPv4 address, UDP socket)
    clientsocket.settimeout(timeout)  # setting max timeout for the sending file
    clientsocket.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 65536)  # send buffer increment to 64KB

    #first check that file sending exists or not
    if not os.path.isfile(filepath):
        raise FileNotFoundError(f"file not found:{filepath}")
    
    #extracting the name of the file to send to reciever
    filename=os.path.basename(filepath)
    log(f"Preparing to send '{os.path.basename(filepath)}' to {dest_ip}:{port_no}")  # Log message

    # ***********************************************************
    # --------------------- HANDSHAKE START ---------------------
    # ***********************************************************

    # send SYN with filename, total size and window
    filesize = os.path.getsize(filepath)
    syn_msg = f"SYN|{filename}|{filesize}|{packet_size}|{window_size}".encode()
    clientsocket.sendto(syn_msg, (dest_ip, port_no))
    log("SYN sent")

    # wait for SYN-ACK
    try:
        resp, _ = clientsocket.recvfrom(2048)
    except socket.timeout:
        clientsocket.close()
        raise TimeoutError("No SYN-ACK from receiver")

    if not resp.startswith(b"SYN-ACK"):
        clientsocket.close()
        raise ConnectionError("Unexpected response during handshake")

    start_seq = int(resp.decode().split("|")[1])
    log(f"SYN-ACK received, start_seq={start_seq}")

    # send ACK to complete handshake
    ack_msg = f"ACK|{start_seq}".encode()
    clientsocket.sendto(ack_msg, (dest_ip, port_no))
    log("ACK sent, handshake complete")

    # *********************************************************
    # --------------------- HANDSHAKE END ---------------------
    # *********************************************************

    #open the file in read binary mode (to send all file types)
    with open(filepath,"rb") as f:  # open filepath means can open any file that is not in the current folder
        # read whole file into chunks so we can retransmit easily on timeout
        chunks = []  # list to hold file pieces in chunks
        while True:
            data = f.read(packet_size)     # sends upto chosen bytes of data at once
            if not data:
                break
            chunks.append(data)     # store this chunk for possible retransmit

        total = len(chunks)        # total number of packets to send
        base_chunk = 0             # index of first unacked chunk
        next_chunk = 0             # next chunk index to send
        retries = 0                # retry counter for the unacked packet
        sent_packets = {}          # keep the actual packets keyed by sequence number

        # map chunk index -> sequence number
        # start_seq stays as negotiated in handshake

        clientsocket.settimeout(timeout)    # ensure socket timeout used for waiting acks

        # send packets using Go-Back-N sliding window
        while base_chunk < total:
            # send packets until the window is full or no more chunks of file
            while next_chunk < total and (next_chunk - base_chunk) < window_size:
                seq_for_chunk = start_seq + next_chunk
                packet = f"{seq_for_chunk}|".encode() + chunks[next_chunk]  # add sequence number to the chunk
                clientsocket.sendto(packet,(dest_ip,port_no))        # send packet with seq number
                log(f"Sent packet {seq_for_chunk} (Window chunks: {base_chunk}-{base_chunk+window_size-1})")    # Log message
                sent_packets[seq_for_chunk] = packet    # save packet for retransmit keyed by seq number
                next_chunk += 1

            # wait for an ack from receiver for the unacked packet
            try:
                ack_from_server, _ = clientsocket.recvfrom(1024)
                # check for ack format
                if ack_from_server.startswith(b"ack"):
                    # decode ack number from bytes like b"ack5"
                    try:
                        ack_num = int(ack_from_server[3:].decode())  # extract number after 'ack'
                    except ValueError:
                        # ignore malformed ack
                        continue

                    # convert ack sequence number to chunk index
                    ack_index = ack_num - start_seq

                    # cumulative ack: move base_chunk if ack is received to send new data
                    if ack_index >= base_chunk:
                        base_chunk = ack_index + 1    # slide window forward past acknowledged chunks
                        retries = 0           # reset retries because forward progress happened
                        log(f"ACK {ack_num} received, sliding window base_chunk to {base_chunk}")    # Log message

                        # now deleting temp packets from sent_packets dict for acknowledged seqs
                        for s in list(sent_packets.keys()):
                            if s <= ack_num:
                                del sent_packets[s]
            except socket.timeout:
                # timeout: retransmit all packets in current window (Go-Back-N)
                log(f"Timeout waiting for ACK. Retransmitting window (chunk {base_chunk} to {next_chunk-1}) [Retry {retries}]") # Log message
                retries += 1
                if retries >= max_retries:
                    clientsocket.close()
                    raise TimeoutError(f"No ack from {dest_ip}:{port_no}! Transfer aborted.")
                # retransmit packets from base_chunk up to next_chunk - 1
                for chunk_idx in range(base_chunk, next_chunk):
                    seq = start_seq + chunk_idx
                    if seq in sent_packets:
                        clientsocket.sendto(sent_packets[seq], (dest_ip, port_no))
                        log(f"Resent packet {seq}")    # Log message
                    else:
                        # rebuild packet if for some reason it's missing
                        packet = f"{seq}|".encode() + chunks[chunk_idx]
                        clientsocket.sendto(packet, (dest_ip, port_no))
                        sent_packets[seq] = packet
                        log(f"Resent rebuilt packet {seq}")    # Log message

    clientsocket.sendto(b"END",(dest_ip,port_no))
    clientsocket.close()
    log('File Sent Successfully!')


# -----------------------------------------------------------------
# --------------------- RECEIVE FILE FUNCTION ---------------------
# -----------------------------------------------------------------
def receive_file(port=9999, save_dir=".", enable_log=False, log_callback=None):
    # Log Function
    def log(msg):
        if enable_log:
            if log_callback:
                log_callback(msg)
            else:
                print(msg)

    serversocket=socket.socket(socket.AF_INET, socket.SOCK_DGRAM)    # create a UDP socket
    serversocket.bind(("0.0.0.0", port))     # bind to socket for listening (0.0.0.0 for all networks)
    serversocket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 65536)  # receive buffer increment to 64KB

    # ***********************************************************
    # --------------------- HANDSHAKE START ---------------------
    # ***********************************************************
    log(f"Receiver started on port {port}, waiting for SYN...") # Log message

    while True:
        data, addr = serversocket.recvfrom(4096)

        # process SYN message
        if data.startswith(b"SYN"):
            parts = data.decode().split("|")
            filename = parts[1]
            filesize = int(parts[2])
            packet_size = int(parts[3])
            window = int(parts[4])
            log(f"SYN received for file '{filename}', size={filesize}, window={window} from {addr[0]}")
            break
        else:
            # ignore all other packets until handshake
            continue

    # send SYN-ACK with starting sequence number
    start_seq = 0
    synack = f"SYN-ACK|{start_seq}".encode()
    serversocket.sendto(synack, addr)
    log("SYN-ACK sent") # Log message

    # wait for ACK from sender
    try:
        ack, addr = serversocket.recvfrom(1024)
    except socket.timeout:
        serversocket.close()
        raise TimeoutError("No ACK received, handshake failed")

    if not ack.startswith(b"ACK"):
        serversocket.close()
        raise ConnectionError("Unexpected response instead of ACK")

    log("ACK received, handshake complete") # Log message   

    expected_seq = start_seq    # Starting sequence number for receiving packets (for duplicate handling)

    # now file is safe to create
    savepath = os.path.join(save_dir, filename)
    log(f"Handshake done, preparing to save file as '{savepath}'")
    
    # *********************************************************
    # --------------------- HANDSHAKE END ---------------------
    # *********************************************************
    
    #now writing to savefile
    with open(savepath,"wb") as f:
        while True:
            data, addr = serversocket.recvfrom(packet_size+100) # extra space for buffer 
            if data == b"END":
                break
            seq_str, file_data = data.split(b"|", 1)  # split at the first '|' which separates sequence number and file data
            seq_num = int(seq_str.decode())      # convert sequence number back to integer (decode)
            log(f"Packet {seq_str.decode()} received from {addr}")  # Log message
            
            if seq_num == expected_seq:
                f.write(file_data)               # write file data to receiving file
                expected_seq += 1                # increment expected sequence number
                # send ack for this packet (in-order packet)
                ack = f"ack{seq_num}".encode()   # create an ack with sequence number
                serversocket.sendto(ack,addr)    # sends ack back to sender with sequence number
                # Log messages
                log(f"In-order packet {seq_num} written, expected_seq updated to {expected_seq}")
                log(f"ACK {seq_num} sent")

            
            elif seq_num < expected_seq:
                # duplicate packet arrived, re-ack that packet so sender can move on
                ack = f"ack{seq_num}".encode()   # ack duplicate so sender knows this was received
                serversocket.sendto(ack,addr)    # send duplicate ack back
                log(f"Duplicate packet {seq_num} received, re-ACK sent")    # log message
            
            else:
                # out-of-order packet arrived i.e. missing earlier packets (seq_num > expected_seq)
                # Go-Back-N behavior: ignore data as it is out of order and re-ack last in-order packet
                last_in_order = expected_seq - 1
                ack = f"ack{last_in_order}".encode()  # ack the last in-order packet index
                serversocket.sendto(ack,addr)         # tell sender what we have up to now
                log(f"Out-of-order packet {seq_num} received, re-ACK last in-order {last_in_order}")    # Log message
    serversocket.close()
    log(f"File transfer completed. FILE SAVED AS: {savepath}")  # Log message
