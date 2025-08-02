import asyncio
import json
import logging
import uuid
from datetime import datetime
from typing import Dict, List, Set, Optional
import websockets
from websockets.server import WebSocketServerProtocol
import sqlite3
import os
from dataclasses import dataclass, asdict
from enum import Enum

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class UserRole(Enum):
    USER = "user"
    ADMIN = "admin"
    MODERATOR = "moderator"

@dataclass
class User:
    id: str
    username: str
    role: UserRole
    connected_at: datetime
    last_seen: datetime
    is_online: bool = True
    avatar: str = ""
    theme: str = "dark"

@dataclass
class Message:
    id: str
    user_id: str
    username: str
    content: str
    timestamp: datetime
    message_type: str = "text"
    attachments: List[str] = None
    reply_to: Optional[str] = None

class ChatServer:
    def __init__(self, host="localhost", port=8765):
        self.host = host
        self.port = port
        self.clients: Dict[str, WebSocketServerProtocol] = {}
        self.users: Dict[str, User] = {}
        self.messages: List[Message] = []
        self.rooms: Dict[str, Set[str]] = {"general": set()}
        self.admin_users: Set[str] = set()
        self.db_path = "chat_database.db"
        self.init_database()
        
    def init_database(self):
        """Initialize SQLite database for persistent storage"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Create users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                role TEXT NOT NULL,
                connected_at TEXT NOT NULL,
                last_seen TEXT NOT NULL,
                avatar TEXT,
                theme TEXT DEFAULT 'dark'
            )
        ''')
        
        # Create messages table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                username TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                message_type TEXT DEFAULT 'text',
                attachments TEXT,
                reply_to TEXT,
                room TEXT DEFAULT 'general'
            )
        ''')
        
        # Create admin users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS admin_users (
                user_id TEXT PRIMARY KEY,
                permissions TEXT NOT NULL
            )
        ''')
        
        conn.commit()
        conn.close()
        
        # Load existing admin users
        self.load_admin_users()
    
    def load_admin_users(self):
        """Load admin users from database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM admin_users")
        admin_ids = cursor.fetchall()
        self.admin_users = {row[0] for row in admin_ids}
        conn.close()
    
    def save_user(self, user: User):
        """Save user to database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO users 
            (id, username, role, connected_at, last_seen, avatar, theme)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            user.id, user.username, user.role.value,
            user.connected_at.isoformat(), user.last_seen.isoformat(),
            user.avatar, user.theme
        ))
        conn.commit()
        conn.close()
    
    def save_message(self, message: Message):
        """Save message to database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO messages 
            (id, user_id, username, content, timestamp, message_type, attachments, reply_to, room)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            message.id, message.user_id, message.username,
            message.content, message.timestamp.isoformat(),
            message.message_type, json.dumps(message.attachments or []),
            message.reply_to, "general"
        ))
        conn.commit()
        conn.close()
    
    def load_messages(self, limit: int = 50) -> List[Message]:
        """Load recent messages from database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, user_id, username, content, timestamp, message_type, attachments, reply_to
            FROM messages ORDER BY timestamp DESC LIMIT ?
        ''', (limit,))
        
        messages = []
        for row in cursor.fetchall():
            message = Message(
                id=row[0],
                user_id=row[1],
                username=row[2],
                content=row[3],
                timestamp=datetime.fromisoformat(row[4]),
                message_type=row[5],
                attachments=json.loads(row[6]) if row[6] else [],
                reply_to=row[7]
            )
            messages.append(message)
        
        conn.close()
        return list(reversed(messages))
    
    async def register_client(self, websocket: WebSocketServerProtocol, username: str, role: UserRole = UserRole.USER):
        """Register a new client"""
        user_id = str(uuid.uuid4())
        user = User(
            id=user_id,
            username=username,
            role=role,
            connected_at=datetime.now(),
            last_seen=datetime.now()
        )
        
        self.clients[user_id] = websocket
        self.users[user_id] = user
        self.rooms["general"].add(user_id)
        
        # Save user to database
        self.save_user(user)
        
        # Send welcome message
        welcome_msg = {
            "type": "system",
            "content": f"Welcome {username}! You are now connected to the chat.",
            "timestamp": datetime.now().isoformat()
        }
        await websocket.send(json.dumps(welcome_msg))
        
        # Broadcast user joined
        await self.broadcast({
            "type": "user_joined",
            "user": {
                "id": user_id,
                "username": username,
                "role": role.value
            },
            "timestamp": datetime.now().isoformat()
        }, exclude_user_id=user_id)
        
        # Send recent messages
        recent_messages = self.load_messages(20)
        for msg in recent_messages:
            await websocket.send(json.dumps({
                "type": "message",
                "message": asdict(msg)
            }))
        
        logger.info(f"User {username} connected with ID {user_id}")
        return user_id
    
    async def handle_message(self, websocket: WebSocketServerProtocol, message_data: dict):
        """Handle incoming message from client"""
        try:
            msg_type = message_data.get("type")
            
            if msg_type == "register":
                username = message_data.get("username", "Anonymous")
                role = UserRole.ADMIN if message_data.get("is_admin") else UserRole.USER
                user_id = await self.register_client(websocket, username, role)
                
                # Send user info back
                await websocket.send(json.dumps({
                    "type": "user_registered",
                    "user_id": user_id,
                    "username": username,
                    "role": role.value
                }))
            
            elif msg_type == "message":
                user_id = message_data.get("user_id")
                if user_id not in self.users:
                    return
                
                user = self.users[user_id]
                content = message_data.get("content", "")
                
                if not content.strip():
                    return
                
                # Create message
                message = Message(
                    id=str(uuid.uuid4()),
                    user_id=user_id,
                    username=user.username,
                    content=content,
                    timestamp=datetime.now(),
                    message_type=message_data.get("message_type", "text"),
                    attachments=message_data.get("attachments", []),
                    reply_to=message_data.get("reply_to")
                )
                
                # Save message
                self.messages.append(message)
                self.save_message(message)
                
                # Broadcast message
                await self.broadcast({
                    "type": "message",
                    "message": asdict(message)
                })
                
                # Update user's last seen
                user.last_seen = datetime.now()
                self.save_user(user)
            
            elif msg_type == "typing":
                user_id = message_data.get("user_id")
                if user_id in self.users:
                    await self.broadcast({
                        "type": "typing",
                        "user_id": user_id,
                        "username": self.users[user_id].username,
                        "is_typing": message_data.get("is_typing", True)
                    }, exclude_user_id=user_id)
            
            elif msg_type == "theme_change":
                user_id = message_data.get("user_id")
                theme = message_data.get("theme", "dark")
                if user_id in self.users:
                    self.users[user_id].theme = theme
                    self.save_user(self.users[user_id])
            
            elif msg_type == "admin_command":
                user_id = message_data.get("user_id")
                if user_id in self.admin_users:
                    await self.handle_admin_command(user_id, message_data.get("command", {}))
        
        except Exception as e:
            logger.error(f"Error handling message: {e}")
            await websocket.send(json.dumps({
                "type": "error",
                "message": "An error occurred while processing your message"
            }))
    
    async def handle_admin_command(self, admin_id: str, command: dict):
        """Handle admin commands"""
        cmd_type = command.get("type")
        
        if cmd_type == "kick_user":
            target_user_id = command.get("target_user_id")
            if target_user_id in self.users:
                await self.kick_user(target_user_id, command.get("reason", "Kicked by admin"))
        
        elif cmd_type == "ban_user":
            target_user_id = command.get("target_user_id")
            if target_user_id in self.users:
                await self.ban_user(target_user_id, command.get("reason", "Banned by admin"))
        
        elif cmd_type == "broadcast":
            message = command.get("message", "")
            await self.broadcast({
                "type": "admin_broadcast",
                "message": message,
                "admin": self.users[admin_id].username,
                "timestamp": datetime.now().isoformat()
            })
        
        elif cmd_type == "get_stats":
            stats = {
                "total_users": len(self.users),
                "online_users": len([u for u in self.users.values() if u.is_online]),
                "total_messages": len(self.messages),
                "admin_users": list(self.admin_users)
            }
            
            admin_ws = self.clients.get(admin_id)
            if admin_ws:
                await admin_ws.send(json.dumps({
                    "type": "admin_stats",
                    "stats": stats
                }))
    
    async def kick_user(self, user_id: str, reason: str):
        """Kick a user from the chat"""
        if user_id in self.clients:
            await self.clients[user_id].send(json.dumps({
                "type": "kicked",
                "reason": reason
            }))
            await self.clients[user_id].close()
            await self.remove_client(user_id)
    
    async def ban_user(self, user_id: str, reason: str):
        """Ban a user from the chat"""
        # Implementation for permanent ban
        await self.kick_user(user_id, f"Banned: {reason}")
    
    async def broadcast(self, message: dict, exclude_user_id: str = None):
        """Broadcast message to all connected clients"""
        disconnected = []
        
        for user_id, websocket in self.clients.items():
            if user_id != exclude_user_id:
                try:
                    await websocket.send(json.dumps(message))
                except websockets.exceptions.ConnectionClosed:
                    disconnected.append(user_id)
                except Exception as e:
                    logger.error(f"Error broadcasting to {user_id}: {e}")
                    disconnected.append(user_id)
        
        # Remove disconnected clients
        for user_id in disconnected:
            await self.remove_client(user_id)
    
    async def remove_client(self, user_id: str):
        """Remove a client from the server"""
        if user_id in self.clients:
            del self.clients[user_id]
        
        if user_id in self.users:
            user = self.users[user_id]
            user.is_online = False
            user.last_seen = datetime.now()
            self.save_user(user)
            
            # Remove from all rooms
            for room in self.rooms.values():
                room.discard(user_id)
            
            # Broadcast user left
            await self.broadcast({
                "type": "user_left",
                "user": {
                    "id": user_id,
                    "username": user.username
                },
                "timestamp": datetime.now().isoformat()
            })
            
            logger.info(f"User {user.username} disconnected")
    
    async def handle_client(self, websocket: WebSocketServerProtocol, path: str):
        """Handle individual client connection"""
        user_id = None
        
        try:
            async for message in websocket:
                try:
                    data = json.loads(message)
                    await self.handle_message(websocket, data)
                except json.JSONDecodeError:
                    await websocket.send(json.dumps({
                        "type": "error",
                        "message": "Invalid JSON format"
                    }))
        
        except websockets.exceptions.ConnectionClosed:
            logger.info("Client connection closed")
        except Exception as e:
            logger.error(f"Error handling client: {e}")
        finally:
            if user_id:
                await self.remove_client(user_id)
    
    async def start(self):
        """Start the WebSocket server"""
        server = await websockets.serve(
            self.handle_client,
            self.host,
            self.port
        )
        
        logger.info(f"WebSocket server started on ws://{self.host}:{self.port}")
        
        # Keep the server running
        await server.wait_closed()

# Admin users setup
ADMIN_USERS = {
    "admin": "admin123",
    "moderator": "mod123"
}

def setup_admin_users():
    """Setup admin users in the database"""
    conn = sqlite3.connect("chat_database.db")
    cursor = conn.cursor()
    
    for username, password in ADMIN_USERS.items():
        user_id = str(uuid.uuid4())
        cursor.execute('''
            INSERT OR REPLACE INTO admin_users (user_id, permissions)
            VALUES (?, ?)
        ''', (user_id, "all"))
        
        # Create admin user
        cursor.execute('''
            INSERT OR REPLACE INTO users 
            (id, username, role, connected_at, last_seen, avatar, theme)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            user_id, username, UserRole.ADMIN.value,
            datetime.now().isoformat(), datetime.now().isoformat(),
            "", "dark"
        ))
    
    conn.commit()
    conn.close()

if __name__ == "__main__":
    # Setup admin users
    setup_admin_users()
    
    # Start server
    server = ChatServer()
    asyncio.run(server.start())