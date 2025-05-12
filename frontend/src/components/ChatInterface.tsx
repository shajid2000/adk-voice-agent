"use client";

import React, { useState, useEffect, useRef } from "react";
import useWebSocket from "react-use-websocket";
import MessageList from "./MessageList";
import MessageInput from "./MessageInput";
import AudioControls from "./AudioControls";

interface Message {
  id: string;
  text: string;
  isUser: boolean;
}

export default function ChatInterface() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const [sessionId, setSessionId] = useState<string>("");
  const [audioMode, setAudioMode] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Generate a random session ID on component mount
  useEffect(() => {
    setSessionId(Math.floor(Math.random() * 1000000).toString());
  }, []);

  // WebSocket connection - using the local proxy
  const { sendMessage, lastMessage } = useWebSocket(
    sessionId ? `/ws/${sessionId}?is_audio=${audioMode}` : null,
    {
      onOpen: () => {
        console.log("WebSocket Connected");
        setIsConnected(true);
      },
      onClose: () => {
        console.log("WebSocket Disconnected");
        setIsConnected(false);
      },
      shouldReconnect: () => true,
    }
  );

  // Handle incoming messages
  useEffect(() => {
    if (lastMessage !== null) {
      try {
        const data = JSON.parse(lastMessage.data);

        // Handle text message
        if (data.mime_type === "text/plain") {
          const newMessage: Message = {
            id: Date.now().toString(),
            text: data.data,
            isUser: false,
          };
          setMessages((prev) => [...prev, newMessage]);
        }

        // Handle audio message (if implementing audio playback)
        else if (data.mime_type === "audio/pcm") {
          // Add audio playback implementation here if needed
          console.log("Received audio data");
        }

        // Handle turn completion
        else if (data.turn_complete) {
          console.log("Agent turn complete");
        }
      } catch (e) {
        console.error("Error parsing WebSocket message:", e);
      }
    }
  }, [lastMessage]);

  // Auto-scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Send a text message
  const sendTextMessage = (text: string) => {
    if (text.trim() === "" || !isConnected) return;

    // Add user message to the UI
    const userMessage: Message = {
      id: Date.now().toString(),
      text: text,
      isUser: true,
    };
    setMessages((prev) => [...prev, userMessage]);

    // Send to WebSocket
    sendMessage(
      JSON.stringify({
        mime_type: "text/plain",
        data: text,
      })
    );
  };

  // Toggle audio mode
  const toggleAudioMode = () => {
    setAudioMode(!audioMode);
    // This will force WebSocket reconnection with the new audio mode
    setSessionId(Math.floor(Math.random() * 1000000).toString());
  };

  return (
    <div className="flex flex-col h-[600px] w-full border border-gray-300 rounded-lg bg-white shadow-lg">
      <div className="p-4 border-b border-gray-300 flex justify-between items-center bg-gray-50">
        <h2 className="text-2xl font-bold text-gray-900">
          ADK Assistant {audioMode ? "(Audio Mode)" : ""}
        </h2>
        <div className="flex items-center">
          <span
            className={`h-3 w-3 rounded-full mr-2 ${
              isConnected ? "bg-green-500" : "bg-red-500"
            }`}
          ></span>
          <span
            className={`font-medium ${
              isConnected ? "text-green-700" : "text-red-700"
            }`}
          >
            {isConnected ? "Connected" : "Disconnected"}
          </span>
        </div>
      </div>

      <MessageList messages={messages} messagesEndRef={messagesEndRef} />

      <div className="border-t border-gray-300 p-4">
        <AudioControls
          audioMode={audioMode}
          toggleAudioMode={toggleAudioMode}
          isConnected={isConnected}
          sendMessage={sendMessage}
        />
        <MessageInput onSendMessage={sendTextMessage} disabled={!isConnected} />
      </div>
    </div>
  );
}
