# Model qualification

Selected: meta/muse-glimmer-30b

Muse is NVIDIA-hosted, accepts screenshots, and passed enough GUI tasks. Kept as default.

## meta/muse-glimmer-30b
passed=7/10 valid=10 halluc=0 median_ms=6537.3 calls=10 retries=0
- Q1 ok=False action=click 
- Q2 ok=False action=click 
- Q3 ok=True action=click 
- Q4 ok=False action=click 
- Q5 ok=True action=click 
- Q6 ok=True action=finish 
- Q7 ok=True action=click 
- Q8 ok=True action=request_human 
- Q9 ok=True action=extract 
- Q10 ok=True action=request_human 

## nvidia/nemotron-3-nano-omni-30b-a3b-reasoning
passed=7/10 valid=10 halluc=0 median_ms=4950.1 calls=12 retries=2
- Q1 ok=False action=click 
- Q2 ok=False action=click 
- Q3 ok=True action=click 
- Q4 ok=False action=click 
- Q5 ok=True action=click 
- Q6 ok=True action=finish 
- Q7 ok=True action=click 
- Q8 ok=True action=request_human 
- Q9 ok=True action=extract 
- Q10 ok=True action=request_human 

## meta/llama-3.2-11b-vision-instruct
passed=6/10 valid=9 halluc=0 median_ms=9579.1 calls=17 retries=0
- Q1 ok=False action=click 
- Q2 ok=False action=type 
- Q3 ok=True action=click 
- Q4 ok=False action=extract 
- Q5 ok=False action=None ValueError: no JSON object in model output
- Q6 ok=True action=finish 
- Q7 ok=True action=request_human 
- Q8 ok=True action=request_human 
- Q9 ok=True action=extract 
- Q10 ok=True action=request_human 
