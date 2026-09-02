import io
import pandas as pd
from typing import List, Dict, Any

class Exporter:
    @staticmethod
    def export_excel(results: List[Dict[str, Any]]) -> bytes:
        """
        Export results to beautifully formatted Excel file
        """
        rows = []
        for r in results:
            rows.append({
                "STT": r.get("index", ""),
                "Input Gốc": r.get("raw_input", ""),
                "Username": r.get("username", ""),
                "Nickname": r.get("nickname", ""),
                "Trạng Thái": r.get("status", ""),
                "Followers": r.get("followers", 0),
                "Following": r.get("following", 0),
                "Tổng Likes (Tim)": r.get("total_likes", 0),
                "Tổng Views (Clip gần nhất)": r.get("total_sample_views", 0),
                "Views Trung Bình / Clip": r.get("avg_sample_views", 0),
                "Tích Xanh": "Có" if r.get("is_verified") else "Không",
                "Riêng Tư": "Có" if r.get("is_private") else "Không",
                "Số Video Mẫu": r.get("video_count_sample", 0),
                "Bio": r.get("bio", ""),
                "Avatar URL": r.get("avatar", ""),
                "Proxy": r.get("proxy_used", ""),
                "Độ Trễ (ms)": r.get("latency_ms", 0),
                "Ghi Chú Lỗi": r.get("error", "")
            })

        df = pd.DataFrame(rows)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='KetQuaCheck')
            workbook = writer.book
            worksheet = writer.sheets['KetQuaCheck']
            
            # Auto-fit columns
            for col in worksheet.columns:
                max_len = 0
                col_letter = col[0].column_letter
                for cell in col:
                    try:
                        if cell.value:
                            max_len = max(max_len, len(str(cell.value)))
                    except:
                        pass
                worksheet.column_dimensions[col_letter].width = max(max_len + 3, 12)

        output.seek(0)
        return output.getvalue()

    @staticmethod
    def export_csv(results: List[Dict[str, Any]]) -> str:
        """
        Export to CSV with UTF-8 BOM for perfect Excel compatibility
        """
        rows = []
        for r in results:
            rows.append({
                "STT": r.get("index", ""),
                "Input": r.get("raw_input", ""),
                "Username": r.get("username", ""),
                "Nickname": r.get("nickname", ""),
                "Status": r.get("status", ""),
                "Followers": r.get("followers", 0),
                "Following": r.get("following", 0),
                "Total_Likes": r.get("total_likes", 0),
                "Total_Views": r.get("total_sample_views", 0),
                "Avg_Views": r.get("avg_sample_views", 0),
                "Verified": r.get("is_verified", False),
                "Private": r.get("is_private", False),
                "Latency_ms": r.get("latency_ms", 0),
                "Error": r.get("error", "")
            })
        df = pd.DataFrame(rows)
        return "\ufeff" + df.to_csv(index=False)

    @staticmethod
    def export_txt(results: List[Dict[str, Any]], format_pattern: str = "{username}|{followers}|{total_likes}|{avg_views}") -> str:
        """
        Export to TXT based on custom format pattern
        Supported variables:
        {raw_input}, {username}, {nickname}, {status}, {followers}, {following},
        {total_likes}, {total_views}, {avg_views}, {is_verified}, {is_private}
        """
        lines = []
        for r in results:
            try:
                line = format_pattern.format(
                    raw_input=r.get("raw_input", ""),
                    username=r.get("username", ""),
                    nickname=r.get("nickname", ""),
                    status=r.get("status", ""),
                    followers=r.get("followers", 0),
                    following=r.get("following", 0),
                    total_likes=r.get("total_likes", 0),
                    total_views=r.get("total_sample_views", 0),
                    avg_views=r.get("avg_sample_views", 0),
                    is_verified=r.get("is_verified", False),
                    is_private=r.get("is_private", False),
                )
                lines.append(line)
            except Exception:
                # Fallback format
                lines.append(f"{r.get('username')}|{r.get('followers')}|{r.get('total_likes')}|{r.get('avg_sample_views')}")
        return "\n".join(lines)
