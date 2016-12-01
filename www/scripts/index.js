$(function(){
  $(document).keypress(function(e){
    var char = String.fromCharCode(e.which)
      , focus = $(':focus')
    console.log(String.fromCharCode(e.which) + ' pressed & ' + focus[0] + ' focused')
    if (char == '~' || char == '`'){
      console.log('tilde activated');
      $('bottom-slide-container').animate({
        top: "calc(100% - 12em)"
      })
    }
  });
});
