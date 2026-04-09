subgraph &quot;VAD Worker Thread&quot;
C --&gt;|Pop 96ms Chunk| D[Spectral Subtraction]
D --&gt; E[Silero VAD ONNX]
E --&gt;|Update State| F{Phát hiện Speech?}
F -- No --&gt; G[Update Noise Profile]
F -- Yes --&gt; H[Buffer Sentence]
H --&gt; I{Silence Limit/Max Length?}
end

I -- Match --&gt; J[Pipeline Hậu xử lý]

subgraph &quot;Post-Processing Pipeline&quot;
J --&gt; K[Adaptive RMS Normalize]
K --&gt; L[Silence Trimming]
L --&gt; M[Whisper Padding 300ms]
M --&gt; N[Soft Clipping/Tanh]
end

N --&gt; O[Base64 Encoding]
O --&gt; P(Callback: Gửi lên Server)