"use client";

import React, { useState, useRef, useEffect } from "react";

interface AudioControlsProps {
  audioMode: boolean;
  toggleAudioMode: () => void;
  isConnected: boolean;
  sendMessage: (message: string) => void;
}

// Helper function to get audio context in a type-safe way
const getAudioContext = (): AudioContext => {
  // Safely handle browser prefixes
  return new (window.AudioContext ||
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (window as any).webkitAudioContext)();
};

export default function AudioControls({
  audioMode,
  toggleAudioMode,
  isConnected,
  sendMessage,
}: AudioControlsProps) {
  const [isRecording, setIsRecording] = useState(false);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);

  // Initialize or reset audio context and media recorder when audio mode changes
  useEffect(() => {
    if (audioMode) {
      // Initialize audio context if needed
      if (!audioContextRef.current) {
        audioContextRef.current = getAudioContext();
      }
    } else {
      // Stop recording if switching away from audio mode
      if (isRecording) {
        stopRecording();
      }
    }

    return () => {
      // Cleanup when component unmounts
      if (mediaRecorderRef.current && isRecording) {
        mediaRecorderRef.current.stop();
      }
    };
  }, [audioMode, isRecording]);

  const startRecording = async () => {
    if (!audioMode || !isConnected) return;

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });

      const mediaRecorder = new MediaRecorder(stream);
      mediaRecorderRef.current = mediaRecorder;

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          // Convert the blob to base64
          const reader = new FileReader();
          reader.readAsDataURL(event.data);
          reader.onloadend = () => {
            const base64Data = (reader.result as string).split(",")[1]; // Remove the data URL prefix

            // Send to WebSocket
            sendMessage(
              JSON.stringify({
                mime_type: "audio/pcm",
                data: base64Data,
              })
            );
          };
        }
      };

      // Get data every 100ms
      mediaRecorder.start(100);
      setIsRecording(true);
    } catch (error) {
      console.error("Error accessing microphone:", error);
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current) {
      mediaRecorderRef.current.stop();

      // Stop the microphone usage
      if (mediaRecorderRef.current.stream) {
        mediaRecorderRef.current.stream
          .getTracks()
          .forEach((track) => track.stop());
      }

      mediaRecorderRef.current = null;
      setIsRecording(false);
    }
  };

  return (
    <div className="mb-4 flex items-center">
      <button
        type="button"
        onClick={toggleAudioMode}
        className={`mr-2 px-4 py-2 border rounded-lg ${
          audioMode ? "bg-purple-500 text-white" : "bg-gray-200 text-gray-700"
        }`}
      >
        {audioMode ? "Disable Audio" : "Enable Audio"}
      </button>

      {audioMode && (
        <button
          type="button"
          onClick={isRecording ? stopRecording : startRecording}
          disabled={!isConnected}
          className={`px-4 py-2 rounded-lg ${
            isRecording ? "bg-red-500 text-white" : "bg-green-500 text-white"
          } disabled:opacity-50 disabled:cursor-not-allowed`}
        >
          {isRecording ? "Stop Recording" : "Start Recording"}
        </button>
      )}
    </div>
  );
}
