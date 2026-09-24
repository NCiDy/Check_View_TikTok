import { ArrowRight, BadgeCheck, Clock3, MessageCircle, ShieldCheck, Sparkles } from "lucide-react";

const SERVICE_BACKGROUND_URL =
  "https://wpotbxpffxoaamwoqgrt.supabase.co/storage/v1/object/public/avatars/nenmoi1.png";

const ZALO_ORDER_URL = "https://zalo.me/0332172659";

export function ServicesPage() {
  return (
    <section
      className="services-page"
      style={{ backgroundImage: `url("${SERVICE_BACKGROUND_URL}")` }}
    >
      <div className="services-shade" />

      <div className="services-content">
        <div className="services-intro">
          <p className="eyebrow">DỊCH VỤ BAE ENTERTAINMENT</p>
          <h1>Dịch vụ đăng thuê TikTok</h1>
          <p>
            Đồng hành cùng team trong quá trình vận hành kênh. Liên hệ Đức để
            nhận tư vấn và báo giá phù hợp.
          </p>

          <div className="services-points">
            <span><Clock3 size={17} /> Phản hồi nhanh</span>
            <span><ShieldCheck size={17} /> Minh bạch, rõ ràng</span>
            <span><BadgeCheck size={17} /> Hỗ trợ tận tình</span>
          </div>
        </div>

        <aside className="services-order-card">
          <div className="services-order-icon">
            <Sparkles size={24} />
          </div>
          <p className="eyebrow">CẦN HỖ TRỢ?</p>
          <h2>Đặt dịch vụ ngay</h2>
          <p>
            Nhắn trực tiếp Zalo của Đức để được tư vấn nhanh và báo giá chi tiết.
          </p>
          <a
            className="services-order-button"
            href={ZALO_ORDER_URL}
            target="_blank"
            rel="noreferrer"
          >
            <MessageCircle size={20} />
            Đặt ngay qua Zalo
            <ArrowRight size={18} />
          </a>
          <small>Đức sẽ phản hồi khi nhận được tin nhắn.</small>
        </aside>
      </div>
    </section>
  );
}
