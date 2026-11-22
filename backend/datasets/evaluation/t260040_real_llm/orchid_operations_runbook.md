# Quy trình vận hành hệ thống Orchid

## 1. Sao lưu dữ liệu
Cơ sở dữ liệu chính của Orchid được sao lưu toàn phần lúc 1 giờ 30 sáng mỗi ngày và sao lưu gia tăng mỗi 15 phút. Bản sao lưu toàn phần được giữ trong 35 ngày; bản sao lưu gia tăng được giữ trong 7 ngày. Bản sao lưu được lưu tại hai vùng: Hà Nội (chính) và Singapore (dự phòng).

## 2. Mục tiêu khôi phục
Mục tiêu thời gian khôi phục (RTO) của Orchid là 4 giờ. Mục tiêu điểm khôi phục (RPO) là 15 phút. Diễn tập khôi phục thảm họa được thực hiện mỗi quý một lần, vào thứ Bảy tuần thứ hai của tháng đầu quý.

## 3. Phân loại sự cố
Sự cố mức SEV1 là khi toàn bộ hệ thống Orchid ngừng hoạt động hoặc dữ liệu khách hàng có nguy cơ bị lộ; kỹ sư trực phải phản hồi trong 10 phút. Sự cố mức SEV2 là khi một chức năng chính bị suy giảm; thời gian phản hồi là 30 phút. Sự cố mức SEV3 là lỗi không ảnh hưởng đến luồng nghiệp vụ chính và được xử lý trong giờ hành chính.

## 4. Trực vận hành
Lịch trực vận hành luân phiên theo tuần, bắt đầu lúc 10 giờ sáng thứ Hai. Mỗi ca trực gồm một kỹ sư chính và một kỹ sư dự phòng. Kỹ sư trực nhận phụ cấp 500.000 đồng cho mỗi ngày trực ngoài giờ hành chính.

## 5. Triển khai phần mềm
Việc triển khai lên môi trường production chỉ được thực hiện từ thứ Hai đến thứ Năm, trước 15 giờ. Không triển khai vào thứ Sáu, cuối tuần và ngày lễ, trừ bản vá khẩn cấp cho sự cố SEV1. Mỗi lần triển khai phải có ít nhất hai người phê duyệt pull request.
