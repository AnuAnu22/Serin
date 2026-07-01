"""Voice system initialization during bot startup."""

        # TIER 6: Initialize voice components
        if config.ENABLE_VOICE and voice_available:
            logger.info("=" * 60)
            logger.info("INITIALIZING VOICE INPUT")
            logger.info("=" * 60)

            # 1. Whisper Transcriber
            transcriber = WhisperTranscriber()

            # 2. Voice Memory Pipeline
            voice_pipeline = VoiceMemoryPipeline(
                memory_system=memory_system,
                background_processor=None,
                message_manager=message_manager
            )

            # 3. Audio Stream Processor
            audio_processor = AudioStreamProcessor(
                transcriber=transcriber,
                voice_pipeline=voice_pipeline,
                silence_threshold=1.5,
                llm_connector=serin.pipeline.think.response_generator.llama
            )

            # 4. Voice Listener
            voice_listener = VoiceListener(client, audio_processor)

            # Start processor
            await audio_processor.start()
            logger.info(f"Voice input system fully initialized! (mode: {config.VOICE_RECEIVER_MODE})")

        # TIER 7: Initialize TTS (if enabled)
        voice_output_manager = None
        if config.ENABLE_TTS:
            logger.info("=" * 60)
            logger.info("INITIALIZING TTS OUTPUT")
            logger.info("=" * 60)

            try:
                tts_engine = TTSEngine()

                # Initialize Voice Manager (for cloning)
                from serin.ops.tts_voice_manager import TTSVoiceManager
                voice_manager = TTSVoiceManager()

                # Initialize Voice Output Manager
                if voice_listener:
                    voice_output_manager = VoiceOutputManager(tts_engine, voice_listener)
                    await voice_output_manager.start()

                    # Attach to Audio Processor (for interrupts)
                    if audio_processor:
                        audio_processor.voice_output_manager = voice_output_manager
                        logger.info("Voice Output Manager attached to Audio Processor")

                    logger.info("Voice Output Manager started!")
                else:
                    logger.warning("Voice Output requires Voice Input (VoiceListener) to be enabled")

            except Exception as e:
                logger.error(f"Failed to initialize TTS: {e}")
                config.ENABLE_TTS = False

        # Initialize MessageManager (SINGLE instance with all dependencies)
        message_manager = EnhancedMessageManagerV3(
            client,
            mention_translator,
            memory_system,
            voice_output_manager=voice_output_manager
        )
        await message_manager.start()
