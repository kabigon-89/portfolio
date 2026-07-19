(function() {
    // 必要なデータを取ってくる
    var endDateStr = fd_data.trigger.current.u_contract_end_date;
    var noticeMonths = parseInt(fd_data.trigger.current.u_notice_period, 10);

    // データチェック
    if (!endDateStr || isNaN(noticeMonths)) {
        return null;
    }

    // 契約満了日から解除変更通知期限を引く
    var gdt = new GlideDateTime(endDateStr);
    var totalSubtractMonths = noticeMonths + 2;
    gdt.addMonthsLocalTime(-totalSubtractMonths);

    // 計算結果をシステムに渡す
    return gdt.getDate();
})();
