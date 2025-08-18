import socket
import threading
import mysql.connector
from database import get_connection
from config import DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME

# Function to handle user registration
def register_user(username, password, display_name, email, avatar):
    conn = get_connection()
    if conn:
        cursor = conn.cursor()
        try:
            cursor.execute("INSERT INTO USERS (Username, Password, Display_name, Status, Email, Avatar) VALUES (%s, %s, %s, %s, %s, %s)", 
                           (username, password, display_name, 'offline', email, avatar))
            conn.commit()
            return True
        except mysql.connector.Error as err:
            print(f"Error: {err}")
            return False
        finally:
            cursor.close()
            conn.close()
    return False

# Function to handle user login
def login_user(username, password):
    conn = get_connection()
    if conn:
        cursor = conn.cursor()
        cursor.execute("SELECT Id, Password FROM USERS WHERE Username = %s", (username,))
        user = cursor.fetchone()
        cursor.close()
        conn.close()
        if user and user[1] == password:
            return user[0]  # Return user ID on success
    return None

# Function to send a message
def send_message(sender_id, receiver_id, room_id, content):
    conn = get_connection()
    if conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO MESSAGES (Sender_id, Receive_id, Room_id, Content, Status) VALUES (%s, %s, %s, %s, %s)",
                       (sender_id, receiver_id, room_id, content, 'sent'))
        conn.commit()
        cursor.close()
        conn.close()
        return True
    return False

# Function to create a chat room
def create_chat_room(creator_id, room_name):
    conn = get_connection()
    if conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO CHAT_ROOM (Room_name, Created_by) VALUES (%s, %s)", (room_name, creator_id))
        conn.commit()
        room_id = cursor.lastrowid
        cursor.close()
        conn.close()
        return room_id
    return None

# Function to join a chat room
def join_chat_room(user_id, room_id):
    conn = get_connection()
    if conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO ROOM_MEMBER (Room_id, User_id, Role) VALUES (%s, %s, %s)", 
                       (room_id, user_id, 'member'))
        conn.commit()
        cursor.close()
        conn.close()
        return True
    return False

# Function to handle client communication
def handle_client(client_socket, client_address):
    print(f"New connection from {client_address}")
    try:
        while True:
            # Receive client message
            message = client_socket.recv(1024).decode('utf-8')
            if not message:
                break

            # Process message (e.g., registration, login, sending messages)
            command, *args = message.split(',')

            if command == 'REGISTER':
                # Registration format: REGISTER,username,password,display_name,email,avatar
                username, password, display_name, email, avatar = args
                if register_user(username, password, display_name, email, avatar):
                    client_socket.send("Registration successful!".encode())
                else:
                    client_socket.send("Registration failed!".encode())

            elif command == 'LOGIN':
                # Login format: LOGIN,username,password
                username, password = args
                user_id = login_user(username, password)
                if user_id:
                    client_socket.send(f"Login successful! User ID: {user_id}".encode())
                else:
                    client_socket.send("Login failed!".encode())

            elif command == 'SEND_MESSAGE':
                # Send message format: SEND_MESSAGE,sender_id,receiver_id,room_id,message
                sender_id, receiver_id, room_id, message = map(int, args[:3]) + [args[3]]
                if send_message(sender_id, receiver_id, room_id, message):
                    client_socket.send("Message sent!".encode())
                else:
                    client_socket.send("Message failed!".encode())

            elif command == 'CREATE_ROOM':
                # Create room format: CREATE_ROOM,creator_id,room_name
                creator_id, room_name = map(int, args[:1]) + [args[1]]
                room_id = create_chat_room(creator_id, room_name)
                if room_id:
                    client_socket.send(f"Room created! Room ID: {room_id}".encode())
                else:
                    client_socket.send("Room creation failed!".encode())

            elif command == 'JOIN_ROOM':
                # Join room format: JOIN_ROOM,user_id,room_id
                user_id, room_id = map(int, args)
                if join_chat_room(user_id, room_id):
                    client_socket.send("Joined room!".encode())
                else:
                    client_socket.send("Failed to join room!".encode())

    except Exception as e:
        print(f"Error: {e}")
    finally:
        client_socket.close()

# Function to start the server
def start_server(host, port):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((host, port))
    server.listen(5)
    print(f"Server started on {host}:{port}")

    while True:
        client_socket, client_address = server.accept()
        thread = threading.Thread(target=handle_client, args=(client_socket, client_address))
        thread.start()

# Run the server
if __name__ == "__main__":
    start_server(DB_HOST, 5000)  # Assuming the server runs on port 5000
