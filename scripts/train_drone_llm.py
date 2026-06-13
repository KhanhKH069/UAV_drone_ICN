"""
scripts/train_drone_llm.py
Fine-tuning Llama 3 8B cho bài toán UAV Intent Classification
Sử dụng Unsloth (4-bit LoRA) để tiết kiệm VRAM cho RTX A4000 16GB.

Cách chạy:
  1. Cài đặt môi trường:
     pip install -r scripts/requirements-train.txt
  2. Chạy script:
     python scripts/train_drone_llm.py

Kết quả đầu ra sẽ là một file `drone_llama3_q4_k_m.gguf` dùng trực tiếp cho Ollama.
"""

import json
from datasets import Dataset
from trl import SFTTrainer
from transformers import TrainingArguments
from unsloth import FastLanguageModel, is_bfloat16_supported

# ---------------------------------------------------------
# 1. Cấu hình Model & Dataset
# ---------------------------------------------------------
DATA_PATH = "dataaaa/nlp_intent_corpus_v21_train_ready.json"
MAX_SEQ_LENGTH = 1024  # Câu lệnh Drone thường rất ngắn, 1024 là quá đủ
DTYPE = None  # Tự động chọn (float16/bfloat16)
LOAD_IN_4BIT = True  # Quan trọng nhất để fit vào 16GB VRAM

# Tải bản Llama 3 8B Instruct siêu tốc từ Unsloth
MODEL_NAME = "unsloth/llama-3-8b-Instruct-bnb-4bit"

# Prompt System chung để định hướng cho Llama
SYSTEM_PROMPT = """You are an intelligent drone assistant. Analyze the user's flight command and extract the intent and associated entities. Respond ONLY with a valid JSON object.
Intent must be one of the known classes. Entities must be correctly extracted."""

# Template ChatML (Llama 3 tương thích rất tốt với định dạng này)
PROMPT_TEMPLATE = """<|begin_of_text|><|start_header_id|>system<|end_header_id|>

{system_prompt}<|eot_id|><|start_header_id|>user<|end_header_id|>

{user_command}<|eot_id|><|start_header_id|>assistant<|end_header_id|>

{assistant_response}<|eot_id|>"""


def load_and_format_dataset(json_path):
    print("Loading and formatting dataset...")
    with open(json_path, "r", encoding="utf-8") as f:
        raw_data = json.load(f).get("data", [])

    formatted_data = {"text": []}

    for sample in raw_data:
        # Lấy raw text hoặc clean text
        command = sample.get("clean_text", "")

        # Bọc Output lại dưới dạng JSON string để ép LLM trả JSON
        intent = sample.get("intent_auto", "unknown")
        entities = sample.get("entities_auto", {})

        output_dict = {"intent": intent, "entities": entities, "confidence": 0.99}
        output_json = json.dumps(output_dict, ensure_ascii=False)

        # Format theo ChatML Template
        text = PROMPT_TEMPLATE.format(
            system_prompt=SYSTEM_PROMPT,
            user_command=command,
            assistant_response=output_json,
        )
        formatted_data["text"].append(text)

    return Dataset.from_dict(formatted_data)


# ---------------------------------------------------------
# 2. Quy trình Huấn luyện (Training)
# ---------------------------------------------------------
def main():
    print(f"Loading {MODEL_NAME} in 4-bit...")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=MODEL_NAME,
        max_seq_length=MAX_SEQ_LENGTH,
        dtype=DTYPE,
        load_in_4bit=LOAD_IN_4BIT,
    )

    # Thêm cấu hình LoRA Adapter để chỉ train <1% trọng số
    print("Injecting LoRA adapters...")
    model = FastLanguageModel.get_peft_model(
        model,
        r=16,  # Rank, số càng cao càng học tốt nhưng tốn VRAM. 16 là vừa vặn.
        target_modules=[
            "q_proj",
            "k_proj",
            "v_proj",
            "o_proj",
            "gate_proj",
            "up_proj",
            "down_proj",
        ],
        lora_alpha=32,
        lora_dropout=0,  # Tối ưu tốc độ = 0
        bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=3407,
        use_rslora=False,
        loftq_config=None,
    )

    dataset = load_and_format_dataset(DATA_PATH)
    print(f"Dataset loaded with {len(dataset)} samples.")

    # Tách Validation Set (10%)
    split_dataset = dataset.train_test_split(test_size=0.1, seed=42)
    train_ds = split_dataset["train"]
    val_ds = split_dataset["test"]

    # Cấu hình Trainer
    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=train_ds,
        eval_dataset=val_ds,
        dataset_text_field="text",
        max_seq_length=MAX_SEQ_LENGTH,
        dataset_num_proc=2,
        packing=False,  # Set True có thể tăng tốc nếu data siêu dài, nhưng Drone data thì False là chuẩn
        args=TrainingArguments(
            per_device_train_batch_size=4,  # Batch nhỏ chống tràn VRAM
            gradient_accumulation_steps=4,  # Bù lại bằng gradient_accumulation
            warmup_steps=50,
            max_steps=300,  # Demo: Train 300 steps. Tăng lên 1000-2000 cho final run
            learning_rate=2e-4,
            fp16=not is_bfloat16_supported(),
            bf16=is_bfloat16_supported(),  # RTX A4000 ko hỗ trợ bfloat16, sẽ tự fallback về fp16
            logging_steps=10,
            evaluation_strategy="steps",
            eval_steps=50,
            optim="adamw_8bit",  # Optimizer 8-bit tiết kiệm VRAM
            weight_decay=0.01,
            lr_scheduler_type="linear",
            seed=3407,
            output_dir="outputs",
        ),
    )

    # Bắt đầu Train
    print("🚀 Bắt đầu huấn luyện mô hình...")
    trainer_stats = trainer.train()
    print(f"Huấn luyện xong: {trainer_stats}")

    # ---------------------------------------------------------
    # 3. Lưu & Đóng gói ra GGUF (Cho Ollama)
    # ---------------------------------------------------------
    print("💾 Đang lưu mô hình dạng LoRA Adapter...")
    model.save_pretrained("drone_lora_model")  # Lưu LoRA weights
    tokenizer.save_pretrained("drone_lora_model")

    print("📦 Đang đóng gói ra file GGUF (q4_k_m) để chạy trong Ollama...")
    # Phương thức này của Unsloth cực mạnh: Gộp LoRA + Model gốc -> GGUF 4bit
    model.save_pretrained_gguf("drone_model", tokenizer, quantization_method="q4_k_m")
    print("✅ Hoàn tất! File GGUF đã được tạo trong thư mục `drone_model`.")
    print("\n---------------------------------------------------------")
    print("💡 Hướng dẫn đưa vào Ollama:")
    print("1. Tạo file Modelfile (nội dung: FROM ./drone_model/unsloth.Q4_K_M.gguf)")
    print("2. Chạy lệnh: ollama create paraline-drone-ai -f Modelfile")
    print("---------------------------------------------------------")


if __name__ == "__main__":
    main()
