from django.shortcuts import render
COPY={
    'en':{'title':'We could not complete this request','body':'Please try again or contact your JAHEZ administrator with the request ID.','back':'Back to tracking','reference':'Request ID'},
    'ar':{'title':'تعذر إكمال هذا الطلب','body':'يرجى المحاولة مجدداً أو التواصل مع مسؤول جاهز مع رقم الطلب.','back':'العودة إلى التتبع','reference':'رقم الطلب'},
}
def error_response(request,status,kind='error'):
    lang='en' if request.path.startswith('/en/') else 'ar'
    copy=dict(COPY[lang])
    if kind=='maintenance':
        copy.update(title='Shipping is briefly under maintenance' if lang=='en' else 'تجري صيانة مؤقتة لنظام الشحن',
                    body='Please try again shortly. Your account is retained.' if lang=='en' else 'يرجى المحاولة بعد قليل. يبقى حسابك محفوظاً.')
    return render(request,'errors/error.html',{'lang':lang,'direction':'ltr' if lang=='en' else 'rtl',
        'copy':copy,'status':status,'request_id':getattr(request,'correlation_id','')},status=status)
def bad_request(request,exception):return error_response(request,400)
def permission_denied(request,exception):return error_response(request,403)
def not_found(request,exception):return error_response(request,404)
def server_error(request):return error_response(request,500)
def csrf_failure(request,reason=''):return error_response(request,403)
