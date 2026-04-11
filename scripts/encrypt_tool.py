from cryptography.fernet import Fernet

def generate_security_keys():
    print("==================================================")
    print(" 🛡️ 공공기관 GovOps 보안 키 생성 도구 (AES-256) ")
    print("==================================================\n")

    # 1. 1급 비밀 마스터 키 생성
    master_key = Fernet.generate_key()
    print("🔑 [MASTER_KEY]")
    print(master_key.decode())
    print("-" * 50)

    # 2. 암호화 객체 생성
    cipher_suite = Fernet(master_key)

    # 3. 도커 설정과 일치하는 평문 DB 접속 URL
    # 형식: postgresql+psycopg2://[계정]:[비밀번호]@localhost:5432/[DB명]
    #plain_db_url = "postgresql+psycopg2://gov_user:gov_password@localhost:5432/gov_ops_db"

    # 수정 후 (표준 형식으로 변경)
    plain_db_url = "postgresql://gov_user:gov_password@localhost:5433/gov_ops_db"

    # 4. DB URL 암호화 수행
    encrypted_db_url = cipher_suite.encrypt(plain_db_url.encode())
    print("🔒 [ENCRYPTED_DATABASE_URL]")
    print(encrypted_db_url.decode())
    print("\n==================================================")
    print("📌 [적용 방법]")
    print("위에서 생성된 두 개의 값을 복사하여, 프로젝트 최상단의 '.env' 파일에 붙여넣으세요.")
    print("==================================================")

if __name__ == "__main__":
    generate_security_keys()
