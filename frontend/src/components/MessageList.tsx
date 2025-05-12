"use client";

import React, { RefObject } from "react";

interface Message {
  id: string;
  text: string;
  isUser: boolean;
}

interface MessageListProps {
  messages: Message[];
  messagesEndRef: RefObject<HTMLDivElement>;
}

export default function MessageList({
  messages,
  messagesEndRef,
}: MessageListProps) {
  return (
    <div className="flex-1 p-4 overflow-y-auto">
      {messages.map((message) => (
        <div
          key={message.id}
          className={`mb-4 max-w-[80%] ${
            message.isUser ? "ml-auto" : "mr-auto"
          }`}
        >
          <div
            className={`p-3 rounded-lg ${
              message.isUser
                ? "bg-blue-500 text-white rounded-br-none"
                : "bg-gray-100 text-gray-800 rounded-bl-none"
            }`}
          >
            {message.text}
          </div>
          <div
            className={`text-xs mt-1 ${
              message.isUser ? "text-right" : "text-left"
            }`}
          >
            {message.isUser ? "You" : "Assistant"}
          </div>
        </div>
      ))}
      <div ref={messagesEndRef} />
    </div>
  );
}
