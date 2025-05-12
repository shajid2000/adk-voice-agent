"use client";

import React from "react";
import ChatInterface from "@/components/ChatInterface";

export default function Home() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-between p-6 md:p-24">
      <div className="w-full max-w-5xl">
        <h1 className="text-4xl font-bold text-center mb-8">
          ADK Voice Assistant
        </h1>
        <ChatInterface />
      </div>
    </main>
  );
}
