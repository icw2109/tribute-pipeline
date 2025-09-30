from insights.classifier_pipeline import ClassifierPipeline, PipelineConfig
pipe=ClassifierPipeline(PipelineConfig(enable_self_train=False, enable_zero_shot=False, debug=True))
rec=pipe.classify_text('Contact us at founders@example.com or +1 415-555-1234 for enterprise support growth rate 20%.')
print(rec['text'])
print('piiScrubbed', rec['debug']['piiScrubbed'])
