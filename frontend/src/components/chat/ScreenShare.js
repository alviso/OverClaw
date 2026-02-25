import { useState, useRef, useCallback, useEffect, forwardRef, useImperativeHandle } from "react";
import { Monitor, MonitorOff, Camera } from "lucide-react";

export const ScreenShare = forwardRef(function ScreenShare({ onCapture }, ref) {
  const [sharing, setSharing] = useState(false);
  const [minimized, setMinimized] = useState(false);
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const canvasRef = useRef(null);

  const stopSharing = useCallback(() => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }
    setSharing(false);
    setMinimized(false);
  }, []);

  const startSharing = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getDisplayMedia({
        video: { cursor: "always" },
        audio: false,
      });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
      }
      setSharing(true);
      setMinimized(false);

      stream.getVideoTracks()[0].onended = () => {
        stopSharing();
      };
    } catch (err) {
      if (err.name !== "NotAllowedError") {
        console.error("Screen share error:", err);
      }
    }
  }, [stopSharing]);

  const captureFrame = useCallback(() => {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas || !sharing) return;

    // Wait for video to have dimensions
    if (!video.videoWidth || !video.videoHeight) {
      console.warn("Video not ready yet, retrying...");
      return;
    }

    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const ctx = canvas.getContext("2d");
    ctx.drawImage(video, 0, 0);

    canvas.toBlob(
      (blob) => {
        if (blob && onCapture) {
          onCapture(blob);
          // Flash effect on the preview to confirm capture
          const el = document.querySelector('[data-testid="screen-share-preview"]');
          if (el) {
            el.style.boxShadow = "0 0 0 2px #f59e0b";
            setTimeout(() => { el.style.boxShadow = ""; }, 300);
          }
        }
      },
      "image/jpeg",
      0.85
    );
  }, [sharing, onCapture]);

  // Expose start/stop to parent via ref
  useImperativeHandle(ref, () => ({
    start: startSharing,
    stop: stopSharing,
    capture: captureFrame,
    isSharing: sharing,
  }), [startSharing, stopSharing, captureFrame, sharing]);

  useEffect(() => {
    return () => {
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((t) => t.stop());
      }
    };
  }, []);

  if (!sharing) return null;

  return (
    <>
      <canvas ref={canvasRef} className="hidden" />
      <div
        className="border border-zinc-800/80 bg-zinc-950 rounded-xl overflow-hidden transition-all"
        data-testid="screen-share-preview"
      >
        <div className="flex items-center justify-between px-3 py-1.5 bg-zinc-900/80 border-b border-zinc-800/60">
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
            <span className="text-[11px] text-zinc-400 font-medium">Screen Share</span>
          </div>
          <div className="flex items-center gap-1">
            <button
              onClick={captureFrame}
              className="p-1 rounded text-zinc-500 hover:text-amber-400 hover:bg-zinc-800 transition-colors"
              title="Capture frame and send to agent"
              data-testid="capture-frame-btn"
            >
              <Camera className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={() => setMinimized(!minimized)}
              className="p-1 rounded text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800 transition-colors text-[11px] font-mono"
              data-testid="minimize-share-btn"
            >
              {minimized ? "+" : "\u2212"}
            </button>
            <button
              onClick={stopSharing}
              className="p-1 rounded text-zinc-500 hover:text-rose-400 hover:bg-zinc-800 transition-colors"
              title="Stop sharing"
              data-testid="stop-share-btn"
            >
              <MonitorOff className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>

        {!minimized && (
          <div className="relative bg-black">
            <video
              ref={videoRef}
              autoPlay
              playsInline
              muted
              className="w-full max-h-[200px] object-contain"
            />
          </div>
        )}
      </div>
    </>
  );
});

export function ScreenShareButton({ onClick, disabled, active }) {
  return (
    <button
      data-testid="screen-share-btn"
      onClick={onClick}
      disabled={disabled}
      className={`p-2 transition-colors flex-shrink-0 ${
        active
          ? "text-emerald-400 hover:text-emerald-300"
          : "text-zinc-600 hover:text-zinc-400"
      }`}
      title={active ? "Stop sharing" : "Share screen"}
    >
      {active ? <MonitorOff className="w-4 h-4" /> : <Monitor className="w-4 h-4" />}
    </button>
  );
}
