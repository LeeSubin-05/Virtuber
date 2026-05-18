import subprocess
import sys
import os
from config import SCRIPT_DIR, ensure_dependencies, save_recolored_texture

# 실행할 스크립트 목록 (순서대로)
SCRIPTS = [
    (r"scripts\prompt.py", "프롬프트 생성"),
    (r"scripts\makeVTube_gsdf.py", "파츠 색상 변경"),
    (r"scripts\rename_parts.py", "파츠 이름 변경"),
    (r"scripts\compose_parts.py", "파츠 합성"),
]

def run_script(script_name, description):
    """개별 스크립트 실행"""
    script_path = os.path.join(SCRIPT_DIR, script_name)
    
    print(f"\n{'='*60}")
    print(f"[{len([s for s in SCRIPTS if SCRIPTS.index((s[0], s[1])) < SCRIPTS.index((script_name, description))]) + 1}/{len(SCRIPTS)}] {description} 실행 중...")
    print(f"{'='*60}")
    print(f"스크립트: {script_name}\n")
    
    try:
        result = subprocess.run(
            [sys.executable, script_path],
            cwd=SCRIPT_DIR,
            check=True,
            capture_output=False
        )
        print(f"\n✅ {description} 완료!")
        return True
    except subprocess.CalledProcessError as e:
        print(f"\n❌ {description} 실패! (에러 코드: {e.returncode})")
        return False
    except Exception as e:
        print(f"\n❌ 오류 발생: {e}")
        return False

def main():
    """모든 스크립트를 순차적으로 실행"""
    print("\n" + "="*60)
    print("🎨 VTuber 파츠 처리 파이프라인 시작")
    print("="*60)

    ensure_dependencies()
    
    results = []
    for script_name, description in SCRIPTS:
        success = run_script(script_name, description)
        results.append((script_name, description, success))
        
        if not success:
            print(f"\n⚠️  {description}에서 오류 발생! 파이프라인 중단.")
            break
    
    # 최종 결과 요약
    print("\n" + "="*60)
    print("📊 실행 결과 요약")
    print("="*60)
    
    for script_name, description, success in results:
        status = "✅ 성공" if success else "❌ 실패"
        print(f"{status} - {description} ({script_name})")
    
    total_success = sum(1 for _, _, success in results if success)
    print(f"\n총 {total_success}/{len(SCRIPTS)} 개 스크립트 완료")
    
    if total_success == len(SCRIPTS):
        print("\n🎉 모든 파이프라인이 성공적으로 완료되었습니다!")
        try:
            save_recolored_texture()
        except Exception as e:
            print(f"\n⚠️ texture 저장 중 오류 발생: {e}")
    else:
        print("\n⚠️  일부 스크립트 실행 중 문제 발생.")
    
    print("="*60 + "\n")

if __name__ == "__main__":
    main()
