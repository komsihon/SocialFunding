/**
 *
 */

(() => {
    $('<input id="pack-qty" type="hidden" value="2" name="quantity">').prependTo("#payment-start-flow");
    $('.investor-pack-qty').focus(() => {
        $('.investor-pack-qty').addClass('qty-set');
    });
    $('.btn-buy-investor-pack.payment-start').click(() => {
        if (!$('.investor-pack-qty').hasClass('qty-set')) {
            $('.pack-count-alert').show();
            $('.investor-pack-qty').focus();
            return false;
        }
        let qty = $('.investor-pack-qty').val();
        $('#pack-qty').val(qty);
    })
})();