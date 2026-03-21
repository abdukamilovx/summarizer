# VoiceScribe — Мультиплатформенный AI-транскрибатор

## Обзор проекта

**VoiceScribe** — приложение для записи, транскрипции и анализа разговоров с качеством уровня Wispr Flow и Plaud. Поддержка iOS и Desktop (Windows/macOS), интеграция с Zoom, Skype, Teams, Google Meet.

---

## Содержание

1. [Функциональные требования](#1-функциональные-требования)
2. [Архитектура системы](#2-архитектура-системы)
3. [Технологический стек](#3-технологический-стек)
4. [iOS приложение](#4-ios-приложение)
5. [Desktop приложение](#5-desktop-приложение)
6. [Backend и API](#6-backend-и-api)
7. [Модели транскрипции](#7-модели-транскрипции)
8. [AI-анализ](#8-ai-анализ)
9. [Синхронизация данных](#9-синхронизация-данных)
10. [Безопасность](#10-безопасность)
11. [План разработки](#11-план-разработки)
12. [Референсы и конкуренты](#12-референсы-и-конкуренты)

---

## 1. Функциональные требования

### 1.1 Основные функции

| Функция | Описание | Приоритет |
|---------|----------|-----------|
| Запись аудио | Запись с микрофона и системного звука | P0 |
| Захват Zoom/Skype/Teams | Запись аудио из видеоконференций | P0 |
| Real-time транскрипция | Живая транскрипция во время записи | P0 |
| Пост-обработка записей | Транскрипция загруженных файлов | P1 |
| Идентификация спикеров | Разделение реплик по говорящим | P0 |
| Мультиязычность | 100+ языков, авто-определение | P0 |
| Резюме разговора | AI-саммари ключевых моментов | P0 |
| Извлечение задач | Action items и to-do из разговора | P0 |
| Экспорт | TXT, DOCX, PDF, SRT, JSON | P1 |
| Синхронизация | Между iOS и Desktop | P1 |

### 1.2 Режимы работы

```
┌─────────────────────────────────────────────────────────────┐
│                    РЕЖИМЫ ТРАНСКРИПЦИИ                      │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐     │
│  │   ЛОКАЛЬНЫЙ │    │   ОБЛАЧНЫЙ  │    │   ГИБРИД    │     │
│  │             │    │             │    │             │     │
│  │ • Whisper   │    │ • OpenAI    │    │ • Авто-     │     │
│  │   локально  │    │   Whisper   │    │   выбор     │     │
│  │ • Полная    │    │ • Deepgram  │    │ • По        │     │
│  │   приват-   │    │ • Assembly  │    │   качеству  │     │
│  │   ность     │    │   AI        │    │   связи     │     │
│  │ • Offline   │    │ • Лучшее    │    │ • Fallback  │     │
│  │   работа    │    │   качество  │    │   режимы    │     │
│  └─────────────┘    └─────────────┘    └─────────────┘     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 1.3 Поддерживаемые платформы видеоконференций

- **Zoom** — захват через Virtual Audio Device
- **Microsoft Teams** — системный захват аудио
- **Skype** — WASAPI/CoreAudio захват
- **Google Meet** — браузерный захват + расширение
- **Telegram** — десктопное приложение
- **Discord** — системный аудио захват
- **FaceTime** (iOS) — через Screen Recording API

---

## 2. Архитектура системы

### 2.1 Общая архитектура

```
┌────────────────────────────────────────────────────────────────────────┐
│                           КЛИЕНТЫ                                       │
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│   ┌──────────────────┐              ┌──────────────────┐               │
│   │    iOS App       │              │   Desktop App    │               │
│   │                  │              │                  │               │
│   │ ┌──────────────┐ │              │ ┌──────────────┐ │               │
│   │ │ Swift/SwiftUI│ │              │ │Python/Electron│ │              │
│   │ └──────────────┘ │              │ └──────────────┘ │               │
│   │ ┌──────────────┐ │              │ ┌──────────────┐ │               │
│   │ │ Speech       │ │              │ │faster-whisper│ │               │
│   │ │ Framework    │ │              │ │ (локальный)  │ │               │
│   │ └──────────────┘ │              │ └──────────────┘ │               │
│   │ ┌──────────────┐ │              │ ┌──────────────┐ │               │
│   │ │ WhisperKit   │ │              │ │ WASAPI/      │ │               │
│   │ │ (on-device)  │ │              │ │ CoreAudio    │ │               │
│   │ └──────────────┘ │              │ └──────────────┘ │               │
│   └────────┬─────────┘              └────────┬─────────┘               │
│            │                                  │                        │
│            └──────────────┬───────────────────┘                        │
│                           │                                            │
│                           ▼                                            │
│            ┌──────────────────────────────┐                            │
│            │        API Gateway           │                            │
│            │     (FastAPI / nginx)        │                            │
│            └──────────────┬───────────────┘                            │
│                           │                                            │
└───────────────────────────┼────────────────────────────────────────────┘
                            │
┌───────────────────────────┼────────────────────────────────────────────┐
│                           ▼                                            │
│            ┌──────────────────────────────┐                            │
│            │      BACKEND SERVICES        │                            │
│            └──────────────────────────────┘                            │
│                                                                        │
│   ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  │
│   │Transcription│  │ Speaker     │  │ AI Analysis │  │ Sync        │  │
│   │ Service     │  │ Diarization │  │ Service     │  │ Service     │  │
│   │             │  │ Service     │  │             │  │             │  │
│   │ • Whisper   │  │ • PyAnnote  │  │ • GPT-4o    │  │ • WebSocket │  │
│   │ • Deepgram  │  │ • Resemblyzer│ │ • Claude    │  │ • Firebase  │  │
│   │ • AssemblyAI│  │             │  │ • Gemini    │  │             │  │
│   └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘  │
│                                                                        │
│   ┌─────────────────────────────────────────────────────────────────┐  │
│   │                      DATA LAYER                                  │  │
│   │  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐    │  │
│   │  │ PostgreSQL│  │   Redis   │  │ S3/MinIO  │  │ Pinecone  │    │  │
│   │  │ (метадата)│  │ (кэш/очер)│  │ (аудио)   │  │ (vectors) │    │  │
│   │  └───────────┘  └───────────┘  └───────────┘  └───────────┘    │  │
│   └─────────────────────────────────────────────────────────────────┘  │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Потоки данных

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    FLOW: Запись → Транскрипция → Анализ                  │
└─────────────────────────────────────────────────────────────────────────┘

  ┌─────────┐     ┌──────────┐     ┌───────────┐     ┌──────────┐
  │ Захват  │────▶│ Буфер    │────▶│ VAD       │────▶│ Чанки    │
  │ аудио   │     │ кольцевой│     │ (Silero)  │     │ 30 сек   │
  └─────────┘     └──────────┘     └───────────┘     └────┬─────┘
                                                          │
       ┌──────────────────────────────────────────────────┘
       │
       ▼
  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
  │ Транскрипция│────▶│ Diarization │────▶│ Пост-       │
  │ (Whisper)   │     │ (PyAnnote)  │     │ обработка   │
  └─────────────┘     └─────────────┘     └──────┬──────┘
                                                  │
       ┌──────────────────────────────────────────┘
       │
       ▼
  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
  │ Коррекция   │────▶│ Пунктуация  │────▶│ Форматиро-  │
  │ LLM         │     │ + регистр   │     │ вание       │
  └─────────────┘     └─────────────┘     └──────┬──────┘
                                                  │
       ┌──────────────────────────────────────────┘
       │
       ▼
  ┌─────────────────────────────────────────────────────────┐
  │                    AI АНАЛИЗ                             │
  │                                                         │
  │   ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────┐ │
  │   │ Резюме   │  │ Ключевые │  │ Action   │  │ Темы/  │ │
  │   │          │  │ пункты   │  │ Items    │  │ Теги   │ │
  │   └──────────┘  └──────────┘  └──────────┘  └────────┘ │
  │                                                         │
  └─────────────────────────────────────────────────────────┘
```

---

## 3. Технологический стек

### 3.1 iOS приложение

| Компонент | Технология | Примечание |
|-----------|------------|------------|
| UI Framework | SwiftUI | iOS 16+ |
| Архитектура | MVVM + Clean Architecture | - |
| Аудио захват | AVFoundation, AudioToolbox | - |
| Локальная транскрипция | WhisperKit (Apple Silicon) | On-device ML |
| Speech Recognition | Apple Speech Framework | Fallback |
| Networking | URLSession + Combine | - |
| Persistence | SwiftData / Core Data | - |
| Background Tasks | BGTaskScheduler | - |
| Push Notifications | APNs + Firebase | - |

### 3.2 Desktop приложение

| Компонент | Технология | Примечание |
|-----------|------------|------------|
| Framework | Python + CustomTkinter | Или Electron |
| Аудио захват (Windows) | WASAPI + PyAudioWPatch | Системный звук |
| Аудио захват (macOS) | CoreAudio + BlackHole | Virtual Audio |
| Транскрипция | faster-whisper | GPU ускорение |
| VAD | Silero VAD | Определение речи |
| Speaker Diarization | pyannote.audio | Локально |
| Упаковка | PyInstaller / electron-builder | - |

### 3.3 Backend

| Компонент | Технология | Примечание |
|-----------|------------|------------|
| API Framework | FastAPI | Python 3.11+ |
| Task Queue | Celery + Redis | Async tasks |
| Database | PostgreSQL 15 | + pgvector |
| Cache | Redis 7 | Session, cache |
| File Storage | MinIO / S3 | Audio files |
| Vector DB | Pinecone / Qdrant | Semantic search |
| Monitoring | Prometheus + Grafana | Metrics |
| Logging | ELK Stack | Centralized logs |

### 3.4 AI/ML сервисы

| Задача | Локальное решение | Облачное решение |
|--------|-------------------|------------------|
| Транскрипция | faster-whisper large-v3 | OpenAI Whisper API, Deepgram, AssemblyAI |
| Diarization | pyannote.audio 3.1 | AssemblyAI, AWS Transcribe |
| LLM анализ | Ollama (Llama 3.1) | GPT-4o, Claude 3.5 Sonnet |
| Коррекция текста | — | GPT-4o-mini |

---

## 4. iOS приложение

### 4.1 Структура проекта

```
VoiceScribe-iOS/
├── App/
│   ├── VoiceScribeApp.swift
│   └── AppDelegate.swift
├── Core/
│   ├── Audio/
│   │   ├── AudioRecorder.swift
│   │   ├── AudioSession.swift
│   │   └── SystemAudioCapture.swift
│   ├── Transcription/
│   │   ├── TranscriptionEngine.swift
│   │   ├── WhisperKitManager.swift
│   │   └── SpeechRecognizer.swift
│   ├── Analysis/
│   │   ├── AIAnalyzer.swift
│   │   └── SummaryGenerator.swift
│   └── Networking/
│       ├── APIClient.swift
│       └── WebSocketManager.swift
├── Features/
│   ├── Recording/
│   │   ├── RecordingView.swift
│   │   ├── RecordingViewModel.swift
│   │   └── LiveTranscriptView.swift
│   ├── Library/
│   │   ├── LibraryView.swift
│   │   └── RecordingDetailView.swift
│   ├── Analysis/
│   │   ├── AnalysisView.swift
│   │   └── ActionItemsView.swift
│   └── Settings/
│       └── SettingsView.swift
├── Models/
│   ├── Recording.swift
│   ├── Transcript.swift
│   ├── Speaker.swift
│   └── ActionItem.swift
├── Services/
│   ├── SyncService.swift
│   ├── StorageService.swift
│   └── NotificationService.swift
└── Resources/
    ├── Assets.xcassets
    └── Localizable.strings
```

### 4.2 Ключевые компоненты

#### AudioRecorder.swift
```swift
import AVFoundation
import Combine

class AudioRecorder: NSObject, ObservableObject {
    @Published var isRecording = false
    @Published var audioLevel: Float = 0
    @Published var duration: TimeInterval = 0
    
    private var audioEngine: AVAudioEngine!
    private var inputNode: AVAudioInputNode!
    private var audioFile: AVAudioFile?
    private var timer: Timer?
    
    // Буфер для real-time транскрипции
    private let audioBuffer = RingBuffer<Float>(capacity: 16000 * 30) // 30 сек
    
    func startRecording() async throws {
        let session = AVAudioSession.sharedInstance()
        try await session.setCategory(.playAndRecord, mode: .default)
        try await session.setActive(true)
        
        audioEngine = AVAudioEngine()
        inputNode = audioEngine.inputNode
        
        let format = inputNode.outputFormat(forBus: 0)
        let targetFormat = AVAudioFormat(
            commonFormat: .pcmFormatFloat32,
            sampleRate: 16000,
            channels: 1,
            interleaved: false
        )!
        
        let converter = AVAudioConverter(from: format, to: targetFormat)!
        
        inputNode.installTap(onBus: 0, bufferSize: 1024, format: format) { [weak self] buffer, time in
            self?.processAudioBuffer(buffer, converter: converter, targetFormat: targetFormat)
        }
        
        try audioEngine.start()
        isRecording = true
        startTimer()
    }
    
    private func processAudioBuffer(_ buffer: AVAudioPCMBuffer, 
                                    converter: AVAudioConverter,
                                    targetFormat: AVAudioFormat) {
        // Конвертация в 16kHz mono
        let convertedBuffer = AVAudioPCMBuffer(
            pcmFormat: targetFormat,
            frameCapacity: AVAudioFrameCount(targetFormat.sampleRate * 0.1)
        )!
        
        var error: NSError?
        converter.convert(to: convertedBuffer, error: &error) { inNumPackets, outStatus in
            outStatus.pointee = .haveData
            return buffer
        }
        
        // Добавление в буфер для транскрипции
        if let channelData = convertedBuffer.floatChannelData?[0] {
            let samples = Array(UnsafeBufferPointer(
                start: channelData,
                count: Int(convertedBuffer.frameLength)
            ))
            audioBuffer.append(contentsOf: samples)
        }
        
        // Обновление уровня громкости
        DispatchQueue.main.async {
            self.audioLevel = self.calculateRMS(buffer)
        }
    }
    
    func getAudioChunk(seconds: Double = 30) -> [Float] {
        return audioBuffer.getLast(count: Int(16000 * seconds))
    }
}
```

#### WhisperKitManager.swift
```swift
import WhisperKit
import Combine

class WhisperKitManager: ObservableObject {
    @Published var isModelLoaded = false
    @Published var transcriptionProgress: Double = 0
    
    private var whisperKit: WhisperKit?
    private let modelName = "large-v3"
    
    func loadModel() async throws {
        whisperKit = try await WhisperKit(
            model: modelName,
            verbose: false,
            prewarm: true,
            load: true,
            useBackgroundDownloadSession: true
        )
        
        await MainActor.run {
            isModelLoaded = true
        }
    }
    
    func transcribe(audioSamples: [Float], language: String? = nil) async throws -> TranscriptionResult {
        guard let whisperKit = whisperKit else {
            throw TranscriptionError.modelNotLoaded
        }
        
        let options = DecodingOptions(
            language: language,
            task: .transcribe,
            temperatureFallbackCount: 3,
            sampleLength: 224,
            usePrefillPrompt: true,
            skipSpecialTokens: true,
            withoutTimestamps: false
        )
        
        let results = try await whisperKit.transcribe(
            audioArray: audioSamples,
            decodeOptions: options
        )
        
        return TranscriptionResult(
            text: results.map { $0.text }.joined(separator: " "),
            segments: results.flatMap { $0.segments ?? [] }.map { segment in
                TranscriptSegment(
                    start: segment.start,
                    end: segment.end,
                    text: segment.text,
                    confidence: segment.probability
                )
            },
            language: results.first?.language ?? "unknown"
        )
    }
    
    // Real-time streaming транскрипция
    func streamTranscribe(audioStream: AsyncStream<[Float]>) -> AsyncStream<String> {
        AsyncStream { continuation in
            Task {
                var buffer: [Float] = []
                
                for await chunk in audioStream {
                    buffer.append(contentsOf: chunk)
                    
                    // Транскрибируем каждые 5 секунд
                    if buffer.count >= 16000 * 5 {
                        if let result = try? await transcribe(audioSamples: buffer) {
                            continuation.yield(result.text)
                        }
                        buffer.removeFirst(16000 * 3) // Sliding window
                    }
                }
                
                // Финальный чанк
                if !buffer.isEmpty {
                    if let result = try? await transcribe(audioSamples: buffer) {
                        continuation.yield(result.text)
                    }
                }
                
                continuation.finish()
            }
        }
    }
}
```

#### RecordingView.swift
```swift
import SwiftUI

struct RecordingView: View {
    @StateObject private var viewModel = RecordingViewModel()
    @State private var showingAnalysis = false
    
    var body: some View {
        NavigationStack {
            VStack(spacing: 24) {
                // Визуализация аудио
                AudioWaveformView(level: viewModel.audioLevel)
                    .frame(height: 120)
                
                // Таймер
                Text(viewModel.formattedDuration)
                    .font(.system(size: 64, weight: .thin, design: .monospaced))
                    .foregroundStyle(.primary)
                
                // Live транскрипция
                ScrollView {
                    Text(viewModel.liveTranscript)
                        .font(.body)
                        .padding()
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                .frame(maxHeight: 200)
                .background(Color(.systemGray6))
                .clipShape(RoundedRectangle(cornerRadius: 12))
                
                // Определённые спикеры
                if !viewModel.detectedSpeakers.isEmpty {
                    HStack {
                        ForEach(viewModel.detectedSpeakers) { speaker in
                            SpeakerBadge(speaker: speaker)
                        }
                    }
                }
                
                Spacer()
                
                // Кнопки управления
                HStack(spacing: 40) {
                    // Пауза
                    Button {
                        viewModel.togglePause()
                    } label: {
                        Image(systemName: viewModel.isPaused ? "play.fill" : "pause.fill")
                            .font(.title)
                            .foregroundStyle(.primary)
                    }
                    
                    // Запись/Стоп
                    Button {
                        if viewModel.isRecording {
                            viewModel.stopRecording()
                            showingAnalysis = true
                        } else {
                            viewModel.startRecording()
                        }
                    } label: {
                        Circle()
                            .fill(viewModel.isRecording ? .red : .blue)
                            .frame(width: 80, height: 80)
                            .overlay {
                                if viewModel.isRecording {
                                    RoundedRectangle(cornerRadius: 4)
                                        .fill(.white)
                                        .frame(width: 24, height: 24)
                                } else {
                                    Circle()
                                        .fill(.white)
                                        .frame(width: 24, height: 24)
                                }
                            }
                    }
                    
                    // Закладка
                    Button {
                        viewModel.addBookmark()
                    } label: {
                        Image(systemName: "bookmark.fill")
                            .font(.title)
                            .foregroundStyle(.orange)
                    }
                }
            }
            .padding()
            .navigationTitle("Запись")
            .sheet(isPresented: $showingAnalysis) {
                if let recording = viewModel.lastRecording {
                    AnalysisView(recording: recording)
                }
            }
        }
    }
}

struct AudioWaveformView: View {
    let level: Float
    @State private var bars: [CGFloat] = Array(repeating: 0.1, count: 40)
    
    var body: some View {
        HStack(spacing: 2) {
            ForEach(0..<bars.count, id: \.self) { index in
                RoundedRectangle(cornerRadius: 2)
                    .fill(Color.blue.gradient)
                    .frame(width: 4, height: bars[index] * 100)
            }
        }
        .onChange(of: level) { _, newValue in
            withAnimation(.easeInOut(duration: 0.1)) {
                bars.removeFirst()
                bars.append(CGFloat(max(0.1, newValue)))
            }
        }
    }
}
```

### 4.3 Интеграция с Zoom/FaceTime

Для iOS ограничен доступ к системному аудио. Решения:

1. **Screen Recording API** — запись экрана с аудио
```swift
import ReplayKit

class ScreenRecorder {
    let recorder = RPScreenRecorder.shared()
    
    func startRecordingWithAudio() async throws {
        guard recorder.isAvailable else {
            throw RecordingError.notAvailable
        }
        
        try await recorder.startRecording { sampleBuffer, bufferType, error in
            if bufferType == .audioApp || bufferType == .audioMic {
                self.processAudioSample(sampleBuffer)
            }
        }
    }
}
```

2. **Broadcast Extension** — для захвата аудио других приложений
3. **CallKit Integration** — для телефонных звонков

---

## 5. Desktop приложение

### 5.1 Структура проекта

```
VoiceScribe-Desktop/
├── src/
│   ├── main.py                    # Точка входа
│   ├── app.py                     # Главное окно приложения
│   │
│   ├── audio/
│   │   ├── __init__.py
│   │   ├── capture.py             # WASAPI/CoreAudio захват
│   │   ├── mixer.py               # Микширование каналов
│   │   └── vad.py                 # Voice Activity Detection
│   │
│   ├── transcription/
│   │   ├── __init__.py
│   │   ├── engine.py              # Базовый движок
│   │   ├── whisper_local.py       # faster-whisper
│   │   ├── whisper_api.py         # OpenAI Whisper API
│   │   ├── deepgram.py            # Deepgram API
│   │   └── assemblyai.py          # AssemblyAI
│   │
│   ├── diarization/
│   │   ├── __init__.py
│   │   ├── pyannote_local.py      # Локальная диаризация
│   │   └── speaker_embeddings.py   # Хранение голосовых отпечатков
│   │
│   ├── analysis/
│   │   ├── __init__.py
│   │   ├── summarizer.py          # Резюме
│   │   ├── action_extractor.py    # Извлечение задач
│   │   └── llm_client.py          # Клиент для LLM
│   │
│   ├── ui/
│   │   ├── __init__.py
│   │   ├── main_window.py         # Главное окно
│   │   ├── recording_panel.py     # Панель записи
│   │   ├── transcript_view.py     # Просмотр транскрипта
│   │   ├── analysis_panel.py      # Панель анализа
│   │   ├── settings_dialog.py     # Настройки
│   │   └── components/
│   │       ├── waveform.py        # Визуализация
│   │       ├── speaker_badge.py   # Значок спикера
│   │       └── timeline.py        # Таймлайн
│   │
│   ├── sync/
│   │   ├── __init__.py
│   │   ├── cloud_sync.py          # Синхронизация с облаком
│   │   └── local_storage.py       # Локальное хранение
│   │
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── config.py              # Конфигурация
│   │   ├── logger.py              # Логирование
│   │   └── export.py              # Экспорт в форматы
│   │
│   └── resources/
│       ├── icons/
│       └── styles/
│
├── models/                         # Локальные ML модели
│   ├── whisper-large-v3/
│   ├── silero-vad/
│   └── pyannote-speaker/
│
├── tests/
├── requirements.txt
├── pyproject.toml
└── build.spec                      # PyInstaller spec
```

### 5.2 Ключевые компоненты

#### capture.py — Захват системного аудио
```python
"""
Захват системного аудио и микрофона для Windows и macOS
"""
import numpy as np
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable, Optional
import threading
import queue

@dataclass
class AudioChunk:
    """Чанк аудио данных"""
    data: np.ndarray
    sample_rate: int
    channels: int
    timestamp: float
    source: str  # 'microphone' | 'system' | 'mixed'

class AudioCapture(ABC):
    """Абстрактный класс для захвата аудио"""
    
    def __init__(self, sample_rate: int = 16000, chunk_duration: float = 0.1):
        self.sample_rate = sample_rate
        self.chunk_duration = chunk_duration
        self.is_capturing = False
        self._callbacks: list[Callable[[AudioChunk], None]] = []
        self._audio_queue = queue.Queue()
    
    @abstractmethod
    def start(self) -> None:
        pass
    
    @abstractmethod
    def stop(self) -> None:
        pass
    
    def on_audio(self, callback: Callable[[AudioChunk], None]) -> None:
        self._callbacks.append(callback)
    
    def _emit_audio(self, chunk: AudioChunk) -> None:
        for callback in self._callbacks:
            callback(chunk)


class WASAPICapture(AudioCapture):
    """Захват аудио через WASAPI на Windows"""
    
    def __init__(self, capture_microphone: bool = True, 
                 capture_system: bool = True, **kwargs):
        super().__init__(**kwargs)
        self.capture_microphone = capture_microphone
        self.capture_system = capture_system
        
        self._mic_stream = None
        self._system_stream = None
        self._capture_thread = None
    
    def start(self) -> None:
        import pyaudiowpatch as pyaudio
        
        self._pyaudio = pyaudio.PyAudio()
        self.is_capturing = True
        
        # Настройка захвата микрофона
        if self.capture_microphone:
            self._mic_stream = self._pyaudio.open(
                format=pyaudio.paFloat32,
                channels=1,
                rate=self.sample_rate,
                input=True,
                frames_per_buffer=int(self.sample_rate * self.chunk_duration),
                stream_callback=self._mic_callback
            )
        
        # Настройка захвата системного звука (WASAPI loopback)
        if self.capture_system:
            # Находим устройство loopback
            wasapi_info = self._pyaudio.get_host_api_info_by_type(pyaudio.paWASAPI)
            default_speakers = self._pyaudio.get_device_info_by_index(
                wasapi_info["defaultOutputDevice"]
            )
            
            if not default_speakers["isLoopbackDevice"]:
                # Ищем loopback версию
                for i in range(self._pyaudio.get_device_count()):
                    dev = self._pyaudio.get_device_info_by_index(i)
                    if dev.get("isLoopbackDevice") and \
                       default_speakers["name"] in dev["name"]:
                        default_speakers = dev
                        break
            
            self._system_stream = self._pyaudio.open(
                format=pyaudio.paFloat32,
                channels=default_speakers["maxInputChannels"],
                rate=int(default_speakers["defaultSampleRate"]),
                input=True,
                input_device_index=default_speakers["index"],
                frames_per_buffer=int(self.sample_rate * self.chunk_duration),
                stream_callback=self._system_callback
            )
    
    def _mic_callback(self, in_data, frame_count, time_info, status):
        import pyaudio
        
        audio_data = np.frombuffer(in_data, dtype=np.float32)
        chunk = AudioChunk(
            data=audio_data,
            sample_rate=self.sample_rate,
            channels=1,
            timestamp=time_info['input_buffer_adc_time'],
            source='microphone'
        )
        self._emit_audio(chunk)
        return (in_data, pyaudio.paContinue)
    
    def _system_callback(self, in_data, frame_count, time_info, status):
        import pyaudio
        import librosa
        
        audio_data = np.frombuffer(in_data, dtype=np.float32)
        
        # Конвертация в моно и ресемплинг если нужно
        if len(audio_data.shape) > 1 and audio_data.shape[1] > 1:
            audio_data = np.mean(audio_data, axis=1)
        
        # Ресемплинг если частота не совпадает
        if self._system_stream and hasattr(self, '_system_sample_rate'):
            if self._system_sample_rate != self.sample_rate:
                audio_data = librosa.resample(
                    audio_data, 
                    orig_sr=self._system_sample_rate,
                    target_sr=self.sample_rate
                )
        
        chunk = AudioChunk(
            data=audio_data,
            sample_rate=self.sample_rate,
            channels=1,
            timestamp=time_info['input_buffer_adc_time'],
            source='system'
        )
        self._emit_audio(chunk)
        return (in_data, pyaudio.paContinue)
    
    def stop(self) -> None:
        self.is_capturing = False
        
        if self._mic_stream:
            self._mic_stream.stop_stream()
            self._mic_stream.close()
        
        if self._system_stream:
            self._system_stream.stop_stream()
            self._system_stream.close()
        
        if self._pyaudio:
            self._pyaudio.terminate()


class AudioMixer:
    """Микширование аудио из разных источников"""
    
    def __init__(self, buffer_duration: float = 0.5):
        self.buffer_duration = buffer_duration
        self._mic_buffer: list[AudioChunk] = []
        self._system_buffer: list[AudioChunk] = []
        self._lock = threading.Lock()
    
    def add_chunk(self, chunk: AudioChunk) -> Optional[AudioChunk]:
        """Добавляет чанк и возвращает смикшированный если готов"""
        with self._lock:
            if chunk.source == 'microphone':
                self._mic_buffer.append(chunk)
            elif chunk.source == 'system':
                self._system_buffer.append(chunk)
            
            return self._try_mix()
    
    def _try_mix(self) -> Optional[AudioChunk]:
        """Пытается смикшировать буферы"""
        if not self._mic_buffer or not self._system_buffer:
            return None
        
        # Берём минимальную длину
        mic_data = np.concatenate([c.data for c in self._mic_buffer])
        sys_data = np.concatenate([c.data for c in self._system_buffer])
        
        min_len = min(len(mic_data), len(sys_data))
        
        if min_len < self.buffer_duration * 16000:
            return None
        
        # Микширование с нормализацией
        mixed = (mic_data[:min_len] * 0.7 + sys_data[:min_len] * 0.5)
        mixed = mixed / np.max(np.abs(mixed) + 1e-8)
        
        # Очищаем использованные данные
        self._mic_buffer.clear()
        self._system_buffer.clear()
        
        return AudioChunk(
            data=mixed,
            sample_rate=16000,
            channels=1,
            timestamp=0,
            source='mixed'
        )
```

#### whisper_local.py — Локальная транскрипция
```python
"""
Локальная транскрипция с использованием faster-whisper
"""
import numpy as np
from faster_whisper import WhisperModel
from dataclasses import dataclass
from typing import Optional, Iterator
import threading
import queue

@dataclass
class TranscriptionSegment:
    start: float
    end: float
    text: str
    confidence: float
    language: str
    speaker: Optional[str] = None

@dataclass
class TranscriptionResult:
    text: str
    segments: list[TranscriptionSegment]
    language: str
    duration: float

class WhisperTranscriber:
    """Транскрибатор на базе faster-whisper"""
    
    def __init__(
        self,
        model_size: str = "large-v3",
        device: str = "cuda",  # или "cpu"
        compute_type: str = "float16",  # или "int8" для CPU
        language: Optional[str] = None,  # None = авто-определение
        num_workers: int = 4
    ):
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.language = language
        
        print(f"Загрузка модели {model_size}...")
        self.model = WhisperModel(
            model_size,
            device=device,
            compute_type=compute_type,
            num_workers=num_workers
        )
        print("Модель загружена!")
    
    def transcribe(
        self,
        audio: np.ndarray,
        sample_rate: int = 16000,
        initial_prompt: Optional[str] = None,
        word_timestamps: bool = True,
        vad_filter: bool = True
    ) -> TranscriptionResult:
        """
        Транскрибирует аудио массив
        
        Args:
            audio: numpy array с аудио данными (float32, mono)
            sample_rate: частота дискретизации
            initial_prompt: начальный промпт для контекста
            word_timestamps: включить таймстемпы для слов
            vad_filter: фильтрация тишины
        """
        # Убеждаемся что аудио в правильном формате
        if audio.dtype != np.float32:
            audio = audio.astype(np.float32)
        
        if len(audio.shape) > 1:
            audio = audio.mean(axis=1)
        
        # Транскрибируем
        segments, info = self.model.transcribe(
            audio,
            language=self.language,
            initial_prompt=initial_prompt,
            word_timestamps=word_timestamps,
            vad_filter=vad_filter,
            vad_parameters=dict(
                min_silence_duration_ms=500,
                speech_pad_ms=200
            ),
            beam_size=5,
            best_of=5,
            temperature=[0.0, 0.2, 0.4, 0.6, 0.8, 1.0],
            compression_ratio_threshold=2.4,
            log_prob_threshold=-1.0,
            no_speech_threshold=0.6,
            condition_on_previous_text=True
        )
        
        # Собираем результаты
        result_segments = []
        full_text = []
        
        for segment in segments:
            text = segment.text.strip()
            if text:
                full_text.append(text)
                result_segments.append(TranscriptionSegment(
                    start=segment.start,
                    end=segment.end,
                    text=text,
                    confidence=np.exp(segment.avg_logprob),
                    language=info.language
                ))
        
        return TranscriptionResult(
            text=" ".join(full_text),
            segments=result_segments,
            language=info.language,
            duration=info.duration
        )
    
    def transcribe_stream(
        self,
        audio_stream: Iterator[np.ndarray],
        chunk_duration: float = 5.0,
        overlap: float = 1.0
    ) -> Iterator[TranscriptionSegment]:
        """
        Потоковая транскрипция для real-time
        
        Args:
            audio_stream: итератор чанков аудио
            chunk_duration: длина чанка для транскрипции (сек)
            overlap: перекрытие между чанками (сек)
        """
        buffer = np.array([], dtype=np.float32)
        chunk_samples = int(chunk_duration * 16000)
        overlap_samples = int(overlap * 16000)
        
        last_text = ""
        
        for audio_chunk in audio_stream:
            buffer = np.concatenate([buffer, audio_chunk])
            
            while len(buffer) >= chunk_samples:
                # Берём чанк для транскрипции
                chunk = buffer[:chunk_samples]
                
                # Транскрибируем
                result = self.transcribe(chunk, vad_filter=False)
                
                # Отдаём новые сегменты
                for segment in result.segments:
                    if segment.text not in last_text:
                        yield segment
                
                last_text = result.text
                
                # Сдвигаем буфер с учётом overlap
                buffer = buffer[chunk_samples - overlap_samples:]
        
        # Обрабатываем остаток
        if len(buffer) > 16000:  # минимум 1 секунда
            result = self.transcribe(buffer, vad_filter=False)
            for segment in result.segments:
                if segment.text not in last_text:
                    yield segment


class StreamingTranscriber:
    """Потоковый транскрибатор с очередью"""
    
    def __init__(self, whisper: WhisperTranscriber):
        self.whisper = whisper
        self._audio_queue = queue.Queue()
        self._result_queue = queue.Queue()
        self._is_running = False
        self._thread = None
    
    def start(self):
        self._is_running = True
        self._thread = threading.Thread(target=self._process_loop, daemon=True)
        self._thread.start()
    
    def stop(self):
        self._is_running = False
        if self._thread:
            self._thread.join(timeout=2.0)
    
    def add_audio(self, audio: np.ndarray):
        """Добавляет аудио чанк в очередь"""
        if self._is_running:
            self._audio_queue.put(audio)
    
    def get_transcription(self, timeout: float = 0.1) -> Optional[TranscriptionSegment]:
        """Получает результат транскрипции"""
        try:
            return self._result_queue.get(timeout=timeout)
        except queue.Empty:
            return None
    
    def _process_loop(self):
        """Основной цикл обработки"""
        buffer = np.array([], dtype=np.float32)
        chunk_size = 16000 * 5  # 5 секунд
        
        while self._is_running:
            try:
                audio = self._audio_queue.get(timeout=0.1)
                buffer = np.concatenate([buffer, audio])
                
                if len(buffer) >= chunk_size:
                    result = self.whisper.transcribe(buffer[:chunk_size])
                    for segment in result.segments:
                        self._result_queue.put(segment)
                    buffer = buffer[chunk_size - 16000:]  # 1 сек overlap
                    
            except queue.Empty:
                continue
```

#### pyannote_local.py — Идентификация спикеров
```python
"""
Диаризация спикеров с использованием pyannote.audio
"""
import numpy as np
from pyannote.audio import Pipeline
from pyannote.audio.pipelines import SpeakerDiarization
from pyannote.core import Segment, Annotation
from dataclasses import dataclass
from typing import Optional
import torch

@dataclass
class SpeakerSegment:
    speaker: str
    start: float
    end: float
    confidence: float

class SpeakerDiarizer:
    """Диаризация спикеров"""
    
    def __init__(
        self,
        model_path: str = "pyannote/speaker-diarization-3.1",
        use_auth_token: Optional[str] = None,
        device: str = "cuda"
    ):
        self.device = torch.device(device if torch.cuda.is_available() else "cpu")
        
        print("Загрузка модели диаризации...")
        self.pipeline = Pipeline.from_pretrained(
            model_path,
            use_auth_token=use_auth_token
        )
        self.pipeline.to(self.device)
        print("Модель диаризации загружена!")
    
    def diarize(
        self,
        audio: np.ndarray,
        sample_rate: int = 16000,
        num_speakers: Optional[int] = None,
        min_speakers: int = 1,
        max_speakers: int = 10
    ) -> list[SpeakerSegment]:
        """
        Определяет спикеров в аудио
        
        Args:
            audio: numpy array с аудио
            sample_rate: частота дискретизации
            num_speakers: точное число спикеров (если известно)
            min_speakers: минимальное число спикеров
            max_speakers: максимальное число спикеров
        """
        import tempfile
        import soundfile as sf
        
        # Сохраняем во временный файл (pyannote требует файл)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            sf.write(f.name, audio, sample_rate)
            temp_path = f.name
        
        try:
            # Запускаем диаризацию
            if num_speakers is not None:
                diarization = self.pipeline(
                    temp_path,
                    num_speakers=num_speakers
                )
            else:
                diarization = self.pipeline(
                    temp_path,
                    min_speakers=min_speakers,
                    max_speakers=max_speakers
                )
            
            # Конвертируем результаты
            segments = []
            for turn, _, speaker in diarization.itertracks(yield_label=True):
                segments.append(SpeakerSegment(
                    speaker=speaker,
                    start=turn.start,
                    end=turn.end,
                    confidence=1.0  # pyannote не даёт confidence напрямую
                ))
            
            return segments
            
        finally:
            import os
            os.unlink(temp_path)
    
    def assign_speakers_to_transcript(
        self,
        transcript_segments: list,
        speaker_segments: list[SpeakerSegment]
    ) -> list:
        """
        Присваивает спикеров сегментам транскрипции
        """
        result = []
        
        for trans_seg in transcript_segments:
            # Находим спикера для этого временного отрезка
            mid_time = (trans_seg.start + trans_seg.end) / 2
            speaker = None
            
            for spk_seg in speaker_segments:
                if spk_seg.start <= mid_time <= spk_seg.end:
                    speaker = spk_seg.speaker
                    break
            
            # Копируем сегмент с добавлением спикера
            new_seg = TranscriptionSegment(
                start=trans_seg.start,
                end=trans_seg.end,
                text=trans_seg.text,
                confidence=trans_seg.confidence,
                language=trans_seg.language,
                speaker=speaker or "UNKNOWN"
            )
            result.append(new_seg)
        
        return result


class SpeakerEmbeddingStore:
    """Хранение голосовых отпечатков для идентификации известных спикеров"""
    
    def __init__(self, model_path: str = "pyannote/wespeaker-voxceleb-resnet34-LM"):
        from pyannote.audio import Inference
        
        self.model = Inference(model_path, window="whole")
        self.embeddings: dict[str, np.ndarray] = {}
    
    def add_speaker(self, name: str, audio: np.ndarray, sample_rate: int = 16000):
        """Добавляет голосовой отпечаток спикера"""
        import tempfile
        import soundfile as sf
        
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            sf.write(f.name, audio, sample_rate)
            embedding = self.model(f.name)
            self.embeddings[name] = embedding
        
        import os
        os.unlink(f.name)
    
    def identify_speaker(self, audio: np.ndarray, sample_rate: int = 16000) -> tuple[str, float]:
        """Определяет спикера по голосу"""
        import tempfile
        import soundfile as sf
        from scipy.spatial.distance import cosine
        
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            sf.write(f.name, audio, sample_rate)
            query_embedding = self.model(f.name)
        
        import os
        os.unlink(f.name)
        
        best_match = None
        best_similarity = -1
        
        for name, embedding in self.embeddings.items():
            similarity = 1 - cosine(query_embedding, embedding)
            if similarity > best_similarity:
                best_similarity = similarity
                best_match = name
        
        return best_match, best_similarity
```

#### main_window.py — Главное окно
```python
"""
Главное окно приложения VoiceScribe
"""
import customtkinter as ctk
from typing import Optional
import threading
from datetime import datetime

from audio.capture import WASAPICapture, AudioMixer, AudioChunk
from transcription.whisper_local import WhisperTranscriber, StreamingTranscriber
from diarization.pyannote_local import SpeakerDiarizer
from analysis.summarizer import Summarizer

class MainWindow(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        self.title("VoiceScribe")
        self.geometry("1200x800")
        
        # Инициализация компонентов
        self._init_services()
        self._init_ui()
        
        # Состояние
        self.is_recording = False
        self.current_transcript = []
        self.audio_buffer = []
    
    def _init_services(self):
        """Инициализация сервисов"""
        # Показываем splash screen во время загрузки
        self.show_loading("Загрузка моделей...")
        
        # Загрузка в отдельном потоке
        def load_models():
            self.transcriber = WhisperTranscriber(
                model_size="large-v3",
                device="cuda",
                compute_type="float16"
            )
            self.streaming_transcriber = StreamingTranscriber(self.transcriber)
            
            self.diarizer = SpeakerDiarizer()
            self.summarizer = Summarizer()
            
            self.hide_loading()
        
        thread = threading.Thread(target=load_models, daemon=True)
        thread.start()
    
    def _init_ui(self):
        """Инициализация UI"""
        # Настройка сетки
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        
        # === Верхняя панель ===
        self.top_frame = ctk.CTkFrame(self)
        self.top_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        
        # Кнопка записи
        self.record_btn = ctk.CTkButton(
            self.top_frame,
            text="⏺ Начать запись",
            command=self.toggle_recording,
            width=200,
            height=50,
            font=("Helvetica", 16),
            fg_color="#E53935",
            hover_color="#B71C1C"
        )
        self.record_btn.pack(side="left", padx=10)
        
        # Таймер
        self.timer_label = ctk.CTkLabel(
            self.top_frame,
            text="00:00:00",
            font=("Helvetica", 32, "bold")
        )
        self.timer_label.pack(side="left", padx=20)
        
        # Индикатор источников
        self.sources_frame = ctk.CTkFrame(self.top_frame)
        self.sources_frame.pack(side="left", padx=20)
        
        self.mic_indicator = ctk.CTkLabel(
            self.sources_frame,
            text="🎤 Микрофон",
            font=("Helvetica", 12)
        )
        self.mic_indicator.pack(side="left", padx=5)
        
        self.system_indicator = ctk.CTkLabel(
            self.sources_frame,
            text="🔊 Системный звук",
            font=("Helvetica", 12)
        )
        self.system_indicator.pack(side="left", padx=5)
        
        # Выбор режима транскрипции
        self.mode_var = ctk.StringVar(value="hybrid")
        self.mode_menu = ctk.CTkOptionMenu(
            self.top_frame,
            values=["Локально", "Облако", "Гибрид"],
            variable=self.mode_var,
            width=150
        )
        self.mode_menu.pack(side="right", padx=10)
        
        # === Основная область ===
        self.main_frame = ctk.CTkFrame(self)
        self.main_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)
        self.main_frame.grid_columnconfigure(0, weight=2)
        self.main_frame.grid_columnconfigure(1, weight=1)
        self.main_frame.grid_rowconfigure(0, weight=1)
        
        # Левая часть - транскрипт
        self.transcript_frame = ctk.CTkFrame(self.main_frame)
        self.transcript_frame.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        
        self.transcript_label = ctk.CTkLabel(
            self.transcript_frame,
            text="Транскрипт",
            font=("Helvetica", 16, "bold")
        )
        self.transcript_label.pack(pady=5)
        
        self.transcript_text = ctk.CTkTextbox(
            self.transcript_frame,
            font=("Helvetica", 14),
            wrap="word"
        )
        self.transcript_text.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Правая часть - анализ
        self.analysis_frame = ctk.CTkFrame(self.main_frame)
        self.analysis_frame.grid(row=0, column=1, sticky="nsew", padx=5, pady=5)
        
        # Табы для анализа
        self.analysis_tabview = ctk.CTkTabview(self.analysis_frame)
        self.analysis_tabview.pack(fill="both", expand=True, padx=5, pady=5)
        
        self.summary_tab = self.analysis_tabview.add("Резюме")
        self.actions_tab = self.analysis_tabview.add("Задачи")
        self.speakers_tab = self.analysis_tabview.add("Спикеры")
        
        # Резюме
        self.summary_text = ctk.CTkTextbox(self.summary_tab, wrap="word")
        self.summary_text.pack(fill="both", expand=True)
        
        # Задачи
        self.actions_list = ctk.CTkScrollableFrame(self.actions_tab)
        self.actions_list.pack(fill="both", expand=True)
        
        # Спикеры
        self.speakers_list = ctk.CTkScrollableFrame(self.speakers_tab)
        self.speakers_list.pack(fill="both", expand=True)
        
        # === Нижняя панель ===
        self.bottom_frame = ctk.CTkFrame(self)
        self.bottom_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=10)
        
        # Кнопки экспорта
        self.export_txt_btn = ctk.CTkButton(
            self.bottom_frame,
            text="📄 TXT",
            command=lambda: self.export("txt"),
            width=80
        )
        self.export_txt_btn.pack(side="left", padx=5)
        
        self.export_docx_btn = ctk.CTkButton(
            self.bottom_frame,
            text="📝 DOCX",
            command=lambda: self.export("docx"),
            width=80
        )
        self.export_docx_btn.pack(side="left", padx=5)
        
        self.export_srt_btn = ctk.CTkButton(
            self.bottom_frame,
            text="🎬 SRT",
            command=lambda: self.export("srt"),
            width=80
        )
        self.export_srt_btn.pack(side="left", padx=5)
        
        # Кнопка анализа
        self.analyze_btn = ctk.CTkButton(
            self.bottom_frame,
            text="🤖 Анализировать",
            command=self.run_analysis,
            width=150
        )
        self.analyze_btn.pack(side="right", padx=10)
    
    def toggle_recording(self):
        """Переключение записи"""
        if self.is_recording:
            self.stop_recording()
        else:
            self.start_recording()
    
    def start_recording(self):
        """Начало записи"""
        self.is_recording = True
        self.record_btn.configure(
            text="⏹ Остановить",
            fg_color="#1976D2"
        )
        
        # Инициализация захвата аудио
        self.audio_capture = WASAPICapture(
            capture_microphone=True,
            capture_system=True
        )
        self.audio_mixer = AudioMixer()
        
        # Callback для аудио
        def on_audio(chunk: AudioChunk):
            mixed = self.audio_mixer.add_chunk(chunk)
            if mixed:
                self.audio_buffer.append(mixed.data)
                self.streaming_transcriber.add_audio(mixed.data)
        
        self.audio_capture.on_audio(on_audio)
        self.audio_capture.start()
        self.streaming_transcriber.start()
        
        # Запуск обновления UI
        self._start_time = datetime.now()
        self._update_timer()
        self._update_transcript()
    
    def stop_recording(self):
        """Остановка записи"""
        self.is_recording = False
        self.record_btn.configure(
            text="⏺ Начать запись",
            fg_color="#E53935"
        )
        
        self.audio_capture.stop()
        self.streaming_transcriber.stop()
    
    def _update_timer(self):
        """Обновление таймера"""
        if self.is_recording:
            elapsed = datetime.now() - self._start_time
            hours, remainder = divmod(int(elapsed.total_seconds()), 3600)
            minutes, seconds = divmod(remainder, 60)
            self.timer_label.configure(text=f"{hours:02d}:{minutes:02d}:{seconds:02d}")
            self.after(1000, self._update_timer)
    
    def _update_transcript(self):
        """Обновление транскрипта из очереди"""
        if self.is_recording:
            segment = self.streaming_transcriber.get_transcription()
            if segment:
                speaker_prefix = f"[{segment.speaker}]: " if segment.speaker else ""
                self.transcript_text.insert("end", f"{speaker_prefix}{segment.text}\n")
                self.transcript_text.see("end")
                self.current_transcript.append(segment)
            
            self.after(100, self._update_transcript)
    
    def run_analysis(self):
        """Запуск AI анализа"""
        if not self.current_transcript:
            return
        
        full_text = " ".join([s.text for s in self.current_transcript])
        
        # Запускаем анализ в отдельном потоке
        def analyze():
            # Резюме
            summary = self.summarizer.summarize(full_text)
            self.summary_text.delete("1.0", "end")
            self.summary_text.insert("1.0", summary)
            
            # Задачи
            actions = self.summarizer.extract_actions(full_text)
            for widget in self.actions_list.winfo_children():
                widget.destroy()
            for i, action in enumerate(actions, 1):
                label = ctk.CTkLabel(
                    self.actions_list,
                    text=f"☐ {action}",
                    anchor="w"
                )
                label.pack(fill="x", padx=5, pady=2)
        
        thread = threading.Thread(target=analyze, daemon=True)
        thread.start()
    
    def export(self, format: str):
        """Экспорт в файл"""
        from tkinter import filedialog
        
        extensions = {
            "txt": ("Text files", "*.txt"),
            "docx": ("Word documents", "*.docx"),
            "srt": ("Subtitle files", "*.srt")
        }
        
        filepath = filedialog.asksaveasfilename(
            defaultextension=f".{format}",
            filetypes=[extensions[format]]
        )
        
        if filepath:
            from utils.export import export_transcript
            export_transcript(self.current_transcript, filepath, format)
    
    def show_loading(self, message: str):
        """Показать loading overlay"""
        self.loading_frame = ctk.CTkFrame(self)
        self.loading_frame.place(relx=0.5, rely=0.5, anchor="center")
        
        ctk.CTkLabel(
            self.loading_frame,
            text=message,
            font=("Helvetica", 18)
        ).pack(padx=40, pady=20)
        
        self.loading_progress = ctk.CTkProgressBar(
            self.loading_frame,
            mode="indeterminate"
        )
        self.loading_progress.pack(padx=20, pady=10)
        self.loading_progress.start()
    
    def hide_loading(self):
        """Скрыть loading overlay"""
        if hasattr(self, 'loading_frame'):
            self.loading_progress.stop()
            self.loading_frame.destroy()


if __name__ == "__main__":
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    
    app = MainWindow()
    app.mainloop()
```

---

## 6. Backend и API

### 6.1 Структура API

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI app
│   ├── config.py               # Настройки
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   ├── routes/
│   │   │   ├── transcription.py
│   │   │   ├── analysis.py
│   │   │   ├── recordings.py
│   │   │   ├── sync.py
│   │   │   └── users.py
│   │   └── deps.py             # Зависимости
│   │
│   ├── core/
│   │   ├── security.py         # JWT, auth
│   │   └── exceptions.py
│   │
│   ├── services/
│   │   ├── transcription.py
│   │   ├── diarization.py
│   │   ├── analysis.py
│   │   └── storage.py
│   │
│   ├── models/
│   │   ├── recording.py
│   │   ├── transcript.py
│   │   └── user.py
│   │
│   └── db/
│       ├── session.py
│       └── repositories/
│
├── workers/
│   ├── transcription_worker.py
│   └── analysis_worker.py
│
├── tests/
├── alembic/
├── Dockerfile
└── docker-compose.yml
```

### 6.2 API эндпоинты

```yaml
# OpenAPI спецификация
openapi: 3.0.0
info:
  title: VoiceScribe API
  version: 1.0.0

paths:
  # === Транскрипция ===
  /api/v1/transcribe:
    post:
      summary: Транскрибировать аудио файл
      requestBody:
        content:
          multipart/form-data:
            schema:
              type: object
              properties:
                file:
                  type: string
                  format: binary
                language:
                  type: string
                  nullable: true
                diarization:
                  type: boolean
                  default: true
      responses:
        200:
          description: Результат транскрипции
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/TranscriptionResult'

  /api/v1/transcribe/stream:
    post:
      summary: Потоковая транскрипция через WebSocket
      # WebSocket endpoint

  # === Анализ ===
  /api/v1/analyze:
    post:
      summary: AI анализ транскрипта
      requestBody:
        content:
          application/json:
            schema:
              type: object
              properties:
                transcript_id:
                  type: string
                analysis_types:
                  type: array
                  items:
                    type: string
                    enum: [summary, actions, key_points, topics]
      responses:
        200:
          description: Результаты анализа

  # === Записи ===
  /api/v1/recordings:
    get:
      summary: Список записей пользователя
    post:
      summary: Создать новую запись

  /api/v1/recordings/{id}:
    get:
      summary: Получить запись
    put:
      summary: Обновить запись
    delete:
      summary: Удалить запись

  # === Синхронизация ===
  /api/v1/sync:
    post:
      summary: Синхронизация данных
    get:
      summary: Получить изменения с timestamp

components:
  schemas:
    TranscriptionResult:
      type: object
      properties:
        id:
          type: string
        text:
          type: string
        segments:
          type: array
          items:
            $ref: '#/components/schemas/Segment'
        language:
          type: string
        duration:
          type: number

    Segment:
      type: object
      properties:
        start:
          type: number
        end:
          type: number
        text:
          type: string
        speaker:
          type: string
          nullable: true
        confidence:
          type: number
```

### 6.3 Реализация FastAPI

```python
# app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.api.routes import transcription, analysis, recordings, sync
from app.core.config import settings

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_services()
    yield
    # Shutdown
    await cleanup_services()

app = FastAPI(
    title="VoiceScribe API",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(transcription.router, prefix="/api/v1", tags=["transcription"])
app.include_router(analysis.router, prefix="/api/v1", tags=["analysis"])
app.include_router(recordings.router, prefix="/api/v1", tags=["recordings"])
app.include_router(sync.router, prefix="/api/v1", tags=["sync"])
```

```python
# app/api/routes/transcription.py
from fastapi import APIRouter, UploadFile, File, BackgroundTasks, WebSocket
from fastapi.responses import StreamingResponse
import asyncio

from app.services.transcription import TranscriptionService
from app.services.diarization import DiarizationService

router = APIRouter()

@router.post("/transcribe")
async def transcribe_file(
    file: UploadFile = File(...),
    language: str | None = None,
    diarization: bool = True,
    background_tasks: BackgroundTasks = None
):
    """Транскрибирует загруженный аудио файл"""
    
    # Сохраняем файл
    audio_data = await file.read()
    
    # Транскрибируем
    service = TranscriptionService()
    result = await service.transcribe(
        audio_data,
        language=language
    )
    
    # Диаризация если запрошена
    if diarization:
        diarization_service = DiarizationService()
        speaker_segments = await diarization_service.diarize(audio_data)
        result = diarization_service.assign_speakers(result, speaker_segments)
    
    return result


@router.websocket("/transcribe/stream")
async def transcribe_stream(websocket: WebSocket):
    """WebSocket для потоковой транскрипции"""
    await websocket.accept()
    
    service = TranscriptionService()
    
    try:
        while True:
            # Получаем аудио чанк
            audio_chunk = await websocket.receive_bytes()
            
            # Транскрибируем
            result = await service.transcribe_chunk(audio_chunk)
            
            if result:
                await websocket.send_json({
                    "type": "transcript",
                    "data": result.dict()
                })
                
    except Exception as e:
        await websocket.close(code=1000)
```

---

## 7. Модели транскрипции

### 7.1 Сравнение моделей

| Модель | Размер | Точность | Скорость | Языки | Цена |
|--------|--------|----------|----------|-------|------|
| **Whisper large-v3** | 2.9GB | ★★★★★ | ★★★☆☆ | 100+ | Бесплатно (локально) |
| **Whisper medium** | 1.4GB | ★★★★☆ | ★★★★☆ | 100+ | Бесплатно (локально) |
| **OpenAI Whisper API** | — | ★★★★★ | ★★★★★ | 100+ | $0.006/мин |
| **Deepgram Nova-2** | — | ★★★★★ | ★★★★★ | 36 | $0.0043/мин |
| **AssemblyAI** | — | ★★★★★ | ★★★★★ | 37 | $0.012/мин |
| **WhisperKit (iOS)** | 500MB | ★★★★☆ | ★★★★☆ | 100+ | Бесплатно |

### 7.2 Выбор модели по сценарию

```python
def select_transcription_engine(
    mode: str,
    audio_duration: float,
    has_internet: bool,
    device_capabilities: dict
) -> str:
    """Выбор движка транскрипции"""
    
    if mode == "local":
        # Всегда локально
        if device_capabilities.get("gpu"):
            return "whisper_local_large"
        return "whisper_local_medium"
    
    elif mode == "cloud":
        # Всегда в облаке
        if audio_duration > 60:
            return "assemblyai"  # Лучше для длинных записей
        return "openai_whisper"
    
    else:  # hybrid
        if not has_internet:
            return "whisper_local_medium"
        
        # Короткие записи - локально (быстрее)
        if audio_duration < 30:
            return "whisper_local_large"
        
        # Длинные записи - облако (точнее, параллельно)
        return "deepgram"
```

### 7.3 Пост-обработка для качества Wispr Flow

```python
class TranscriptPostProcessor:
    """Пост-обработка транскрипта для повышения качества"""
    
    def __init__(self, llm_client):
        self.llm = llm_client
    
    async def process(self, transcript: str, language: str = "ru") -> str:
        """
        Полная пост-обработка:
        1. Коррекция ошибок распознавания
        2. Правильная пунктуация
        3. Форматирование параграфов
        4. Исправление регистра
        """
        
        # Промпт для LLM коррекции
        prompt = f"""Исправь транскрипт речи. Задачи:

1. Исправь очевидные ошибки распознавания (например: "в общем-то" вместо "вопщемта")
2. Расставь правильную пунктуацию
3. Исправь регистр (начало предложений, имена собственные)
4. Раздели на логические параграфы
5. НЕ меняй смысл, НЕ добавляй слова, НЕ удаляй информацию

Транскрипт:
{transcript}

Исправленный текст:"""

        corrected = await self.llm.generate(prompt)
        return corrected
    
    def format_with_speakers(
        self,
        segments: list,
        speaker_names: dict[str, str] = None
    ) -> str:
        """Форматирование с именами спикеров"""
        
        result = []
        current_speaker = None
        current_text = []
        
        for seg in segments:
            speaker = speaker_names.get(seg.speaker, seg.speaker) if speaker_names else seg.speaker
            
            if speaker != current_speaker:
                if current_text:
                    result.append(f"**{current_speaker}:** {' '.join(current_text)}")
                current_speaker = speaker
                current_text = [seg.text]
            else:
                current_text.append(seg.text)
        
        if current_text:
            result.append(f"**{current_speaker}:** {' '.join(current_text)}")
        
        return "\n\n".join(result)
```

---

## 8. AI-анализ

### 8.1 Промпты для анализа

```python
# analysis/prompts.py

SUMMARY_PROMPT = """Проанализируй транскрипт разговора и создай структурированное резюме.

ТРАНСКРИПТ:
{transcript}

Создай резюме со следующей структурой:
1. **Краткое содержание** (2-3 предложения)
2. **Основные темы обсуждения**
3. **Ключевые решения** (если были приняты)
4. **Открытые вопросы** (если остались)

Резюме:"""

ACTION_ITEMS_PROMPT = """Извлеки все задачи и action items из транскрипта разговора.

ТРАНСКРИПТ:
{transcript}

Для каждой задачи укажи:
- Описание задачи
- Ответственный (если упоминается)
- Срок (если упоминается)
- Приоритет (высокий/средний/низкий)

Формат ответа - JSON:
{{
  "action_items": [
    {{
      "task": "описание",
      "assignee": "имя или null",
      "deadline": "срок или null",
      "priority": "high/medium/low"
    }}
  ]
}}

JSON:"""

KEY_POINTS_PROMPT = """Выдели ключевые пункты из транскрипта.

ТРАНСКРИПТ:
{transcript}

Выдели 5-10 самых важных пунктов. Каждый пункт должен быть:
- Конкретным
- Информативным
- Кратким (1-2 предложения)

Ключевые пункты:
1."""

TOPICS_PROMPT = """Определи основные темы разговора.

ТРАНСКРИПТ:
{transcript}

Верни список тем в формате JSON:
{{
  "topics": [
    {{
      "name": "название темы",
      "time_percentage": 25,
      "key_points": ["пункт 1", "пункт 2"]
    }}
  ]
}}

JSON:"""
```

### 8.2 Сервис анализа

```python
# analysis/summarizer.py
from openai import AsyncOpenAI
import json
from typing import Optional

class Summarizer:
    """Сервис AI-анализа транскриптов"""
    
    def __init__(
        self,
        model: str = "gpt-4o",
        api_key: Optional[str] = None
    ):
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model
    
    async def summarize(self, transcript: str) -> str:
        """Генерация резюме"""
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "Ты помощник для анализа записей встреч."},
                {"role": "user", "content": SUMMARY_PROMPT.format(transcript=transcript)}
            ],
            temperature=0.3,
            max_tokens=1000
        )
        return response.choices[0].message.content
    
    async def extract_actions(self, transcript: str) -> list[dict]:
        """Извлечение задач"""
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "user", "content": ACTION_ITEMS_PROMPT.format(transcript=transcript)}
            ],
            temperature=0.2,
            max_tokens=1500,
            response_format={"type": "json_object"}
        )
        
        result = json.loads(response.choices[0].message.content)
        return result.get("action_items", [])
    
    async def get_key_points(self, transcript: str) -> list[str]:
        """Выделение ключевых пунктов"""
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "user", "content": KEY_POINTS_PROMPT.format(transcript=transcript)}
            ],
            temperature=0.3
        )
        
        text = response.choices[0].message.content
        points = [p.strip() for p in text.split("\n") if p.strip()]
        return points
    
    async def analyze_topics(self, transcript: str) -> list[dict]:
        """Анализ тем разговора"""
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "user", "content": TOPICS_PROMPT.format(transcript=transcript)}
            ],
            temperature=0.3,
            response_format={"type": "json_object"}
        )
        
        result = json.loads(response.choices[0].message.content)
        return result.get("topics", [])
    
    async def full_analysis(self, transcript: str) -> dict:
        """Полный анализ"""
        import asyncio
        
        summary, actions, key_points, topics = await asyncio.gather(
            self.summarize(transcript),
            self.extract_actions(transcript),
            self.get_key_points(transcript),
            self.analyze_topics(transcript)
        )
        
        return {
            "summary": summary,
            "action_items": actions,
            "key_points": key_points,
            "topics": topics
        }
```

---

## 9. Синхронизация данных

### 9.1 Архитектура синхронизации

```
┌─────────────────────────────────────────────────────────────────┐
│                    СИНХРОНИЗАЦИЯ                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   ┌─────────────┐        ┌─────────────┐        ┌───────────┐  │
│   │   iOS App   │◄──────►│   Backend   │◄──────►│  Desktop  │  │
│   │             │        │             │        │           │  │
│   │ ┌─────────┐ │        │ ┌─────────┐ │        │ ┌───────┐ │  │
│   │ │ Local DB│ │        │ │PostgreSQL│ │       │ │SQLite │ │  │
│   │ └─────────┘ │        │ └─────────┘ │        │ └───────┘ │  │
│   └─────────────┘        └─────────────┘        └───────────┘  │
│          │                      │                     │        │
│          │                      │                     │        │
│          └──────────────────────┼─────────────────────┘        │
│                                 │                               │
│                                 ▼                               │
│                         ┌─────────────┐                         │
│                         │    S3/MinIO │                         │
│                         │  (аудио     │                         │
│                         │   файлы)    │                         │
│                         └─────────────┘                         │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 9.2 Протокол синхронизации

```python
# sync/protocol.py
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from enum import Enum

class SyncOperation(Enum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"

@dataclass
class SyncItem:
    """Элемент для синхронизации"""
    id: str
    type: str  # recording, transcript, analysis
    operation: SyncOperation
    data: dict
    timestamp: datetime
    device_id: str
    version: int

class SyncManager:
    """Менеджер синхронизации"""
    
    def __init__(self, api_client, local_db):
        self.api = api_client
        self.db = local_db
        self.last_sync = None
    
    async def sync(self) -> dict:
        """Полная синхронизация"""
        
        # 1. Получаем локальные изменения
        local_changes = await self.db.get_changes_since(self.last_sync)
        
        # 2. Отправляем на сервер
        server_response = await self.api.sync({
            "changes": [c.to_dict() for c in local_changes],
            "last_sync": self.last_sync.isoformat() if self.last_sync else None,
            "device_id": self.device_id
        })
        
        # 3. Применяем серверные изменения
        conflicts = []
        for change in server_response["changes"]:
            try:
                await self._apply_change(change)
            except ConflictError as e:
                conflicts.append(e)
        
        # 4. Разрешаем конфликты
        if conflicts:
            await self._resolve_conflicts(conflicts)
        
        # 5. Обновляем timestamp
        self.last_sync = datetime.fromisoformat(server_response["sync_timestamp"])
        
        return {
            "synced": len(server_response["changes"]),
            "conflicts": len(conflicts),
            "timestamp": self.last_sync
        }
    
    async def _apply_change(self, change: dict):
        """Применение изменения"""
        item = SyncItem(**change)
        
        # Проверка конфликта версий
        local_item = await self.db.get(item.id)
        if local_item and local_item.version > item.version:
            raise ConflictError(local_item, item)
        
        # Применяем
        if item.operation == SyncOperation.CREATE:
            await self.db.insert(item)
        elif item.operation == SyncOperation.UPDATE:
            await self.db.update(item)
        elif item.operation == SyncOperation.DELETE:
            await self.db.delete(item.id)
    
    async def _resolve_conflicts(self, conflicts: list):
        """Разрешение конфликтов (last-write-wins)"""
        for conflict in conflicts:
            # Сохраняем более новую версию
            if conflict.local.timestamp > conflict.remote.timestamp:
                await self.api.push(conflict.local)
            else:
                await self.db.update(conflict.remote)
```

---

## 10. Безопасность

### 10.1 Шифрование данных

```python
# security/encryption.py
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64
import os

class AudioEncryption:
    """Шифрование аудио файлов"""
    
    def __init__(self, user_password: str):
        self.key = self._derive_key(user_password)
        self.fernet = Fernet(self.key)
    
    def _derive_key(self, password: str) -> bytes:
        """Деривация ключа из пароля"""
        salt = os.urandom(16)  # В реальности - хранить
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=480000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        return key
    
    def encrypt_audio(self, audio_data: bytes) -> bytes:
        """Шифрование аудио"""
        return self.fernet.encrypt(audio_data)
    
    def decrypt_audio(self, encrypted_data: bytes) -> bytes:
        """Расшифровка аудио"""
        return self.fernet.decrypt(encrypted_data)
```

### 10.2 Приватность данных

```yaml
# Политика обработки данных

Локальный режим:
  - Аудио НЕ покидает устройство
  - Транскрипция выполняется локально
  - Данные хранятся только на устройстве
  - Опциональное шифрование файлов

Облачный режим:
  - Аудио передаётся по TLS 1.3
  - Обработка в изолированных контейнерах
  - Данные удаляются после обработки (опционально)
  - Соответствие GDPR

Гибридный режим:
  - Пользователь выбирает для каждой записи
  - Чувствительные записи - локально
  - Обычные - в облаке для лучшего качества
```

---

## 11. План разработки

### 11.1 Roadmap

```
ФАЗА 1: MVP (8 недель)
├── Неделя 1-2: Базовая архитектура
│   ├── Проект iOS (SwiftUI)
│   ├── Проект Desktop (Python)
│   └── Backend scaffolding
│
├── Неделя 3-4: Захват аудио
│   ├── iOS: AVFoundation интеграция
│   ├── Desktop: WASAPI/CoreAudio
│   └── Микширование каналов
│
├── Неделя 5-6: Транскрипция
│   ├── WhisperKit интеграция (iOS)
│   ├── faster-whisper (Desktop)
│   └── Real-time streaming
│
└── Неделя 7-8: MVP release
    ├── Базовый UI
    ├── Локальная транскрипция
    └── Экспорт в TXT

ФАЗА 2: Полная версия (8 недель)
├── Неделя 9-10: Диаризация
│   ├── pyannote.audio интеграция
│   └── Speaker embeddings
│
├── Неделя 11-12: AI анализ
│   ├── Интеграция LLM
│   ├── Резюме, ключевые пункты
│   └── Action items
│
├── Неделя 13-14: Backend & Sync
│   ├── FastAPI backend
│   ├── PostgreSQL
│   └── Синхронизация
│
└── Неделя 15-16: Polish
    ├── UI/UX улучшения
    ├── Тестирование
    └── Документация

ФАЗА 3: Расширение (ongoing)
├── Chrome расширение для Google Meet
├── Zoom SDK интеграция
├── Telegram Bot
├── Apple Watch companion
└── Android версия
```

### 11.2 Приоритеты разработки

| Приоритет | Функция | Платформа | Сложность |
|-----------|---------|-----------|-----------|
| P0 | Запись аудио | iOS + Desktop | Средняя |
| P0 | Локальная транскрипция | iOS + Desktop | Высокая |
| P0 | Real-time отображение | iOS + Desktop | Средняя |
| P1 | Диаризация спикеров | Backend | Высокая |
| P1 | AI резюме | Backend | Средняя |
| P1 | Синхронизация | Все | Высокая |
| P2 | Chrome расширение | Web | Средняя |
| P2 | Zoom интеграция | Desktop | Высокая |

---

## 12. Референсы и конкуренты

### 12.1 Анализ конкурентов

| Продукт | Сильные стороны | Слабые стороны |
|---------|-----------------|----------------|
| **Plaud Note** | Hardware + software, качество записи | Нужен отдельный девайс, цена |
| **Wispr Flow** | Отличная пост-обработка, точность | Только macOS, подписка |
| **Otter.ai** | Реальное время, интеграции | Качество русского языка |
| **Fireflies.ai** | Интеграция с Zoom/Meet | Только облако, privacy |
| **Krisp** | Шумоподавление | Ограниченная транскрипция |

### 12.2 Технические референсы

- **WhisperKit**: https://github.com/argmaxinc/WhisperKit
- **faster-whisper**: https://github.com/SYSTRAN/faster-whisper
- **pyannote.audio**: https://github.com/pyannote/pyannote-audio
- **PyAudioWPatch**: https://github.com/s0d3s/PyAudioWPatch
- **Silero VAD**: https://github.com/snakers4/silero-vad

### 12.3 Полезные ссылки

- OpenAI Whisper: https://platform.openai.com/docs/guides/speech-to-text
- Deepgram API: https://developers.deepgram.com/
- AssemblyAI: https://www.assemblyai.com/docs

---

## Приложения

### A. Требования к окружению

**iOS:**
- iOS 16.0+
- iPhone 12+ (для оптимальной производительности WhisperKit)
- ~500MB для модели Whisper

**Desktop (Windows):**
- Windows 10/11
- Python 3.11+
- NVIDIA GPU (рекомендуется для faster-whisper)
- 8GB RAM минимум, 16GB рекомендуется

**Desktop (macOS):**
- macOS 13.0+ (Ventura)
- Apple Silicon (M1/M2/M3) для оптимальной производительности
- BlackHole для захвата системного звука

### B. Зависимости

```txt
# requirements.txt (Desktop)

# Audio
pyaudiowpatch>=0.2.12  # Windows
sounddevice>=0.4.6
numpy>=1.24.0
librosa>=0.10.0

# Transcription
faster-whisper>=1.0.0
openai>=1.0.0

# Diarization
pyannote.audio>=3.1.0
torch>=2.0.0

# UI
customtkinter>=5.2.0

# Backend client
httpx>=0.25.0
websockets>=12.0

# Utils
python-dotenv>=1.0.0
pydantic>=2.0.0
```

### C. Структура базы данных

```sql
-- Записи
CREATE TABLE recordings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    title VARCHAR(255),
    duration_seconds FLOAT,
    audio_url VARCHAR(512),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    device_id VARCHAR(100),
    sync_version INTEGER DEFAULT 1
);

-- Транскрипты
CREATE TABLE transcripts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    recording_id UUID NOT NULL REFERENCES recordings(id),
    full_text TEXT,
    language VARCHAR(10),
    model_used VARCHAR(50),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Сегменты транскрипта
CREATE TABLE transcript_segments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    transcript_id UUID NOT NULL REFERENCES transcripts(id),
    start_time FLOAT NOT NULL,
    end_time FLOAT NOT NULL,
    text TEXT NOT NULL,
    speaker VARCHAR(50),
    confidence FLOAT,
    INDEX idx_transcript_time (transcript_id, start_time)
);

-- Анализ
CREATE TABLE analyses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    recording_id UUID NOT NULL REFERENCES recordings(id),
    summary TEXT,
    key_points JSONB,
    action_items JSONB,
    topics JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Спикеры (голосовые профили)
CREATE TABLE speaker_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    name VARCHAR(100) NOT NULL,
    embedding VECTOR(256),  -- pgvector
    created_at TIMESTAMP DEFAULT NOW()
);
```

---

*Документ создан: 2025-03-21*
*Версия: 1.0*
