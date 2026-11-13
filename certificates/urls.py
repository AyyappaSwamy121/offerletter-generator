from django.urls import path
from . import views
from . import admin_mgmt_views
from . import college_views

urlpatterns = [
    # Main pages
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('home/', views.home, name='home'),
    path('', views.verify_student, name='verify_student'),
    path('generate/', views.generate_certificate, name='generate_certificate'),
    path('certificates/', views.certificate_list, name='certificate_list'),
    path('about/', views.about, name='about'),
    path('contact/', views.contact, name='contact'),
    path('stats/', views.stats, name='stats'),
    path('upload/', views.upload_excel, name='upload_excel'),
    path('generate-from-db/', views.generate_certificates_from_db, name='generate_certificates_from_db'),
    path('export-certificates/', views.export_certificates_to_excel, name='export_certificates'),
    path('certificates/export/', views.export_certificates, name='export_certificates'),
    path('certificate_list_view/', views.certificate_list_view, name='certificate_list_view'),
    path('download_excel_template/', views.download_excel_template, name='download_excel_template'),
    path('generate-offer-letter/', views.generate_offer_letter, name='generate_offer_letter'),
    path('download-offer-letter-pdf/', views.download_offer_letter_pdf, name='download_offer_letter_pdf'),
    path('download-offer-letter-image/', views.download_offer_letter_image, name='download_offer_letter_image'),
    # Offer letter image by primary key (for records without certificate_id)
    path('offer-letter/<int:pk>/image/', views.download_offer_letter_image_by_id, name='offer_letter_image'),

    # New detail view by primary key
    path('certificate/details/<int:pk>/', views.certificate_detail_by_pk, name='certificate_detail_by_pk'),

    path('certificate/<str:certificate_id>/', views.certificate_detail, name='certificate_detail'),
    path('verify/', views.verify_certificate, name='verify_certificate_base'),
    path('verify/<str:certificate_id>/', views.verify_certificate, name='verify_certificate'),
    path('offer/<str:certificate_id>/', views.verify_certificate, name='offer_certificate'),
    
    # Download endpoints
    path('download/<int:pk>/', views.download_certificate, name='download_certificate'),
    path('download-pdf/<int:pk>/', views.download_certificate_pdf, name='download_certificate_pdf'),
    
    # API endpoints
    path('api/verify/<str:certificate_id>/', views.api_verify_certificate, name='api_verify_certificate'),
    path('api/toggle-email-automation/', views.toggle_email_automation, name='toggle_email_automation'),

    # Super Admin: College Admin Management & Audit Logs
    path('college-admins/', admin_mgmt_views.college_admin_list, name='college_admin_list'),
    path('college-admins/create/', admin_mgmt_views.college_admin_create, name='college_admin_create'),
    path('college-admins/<int:pk>/edit/', admin_mgmt_views.college_admin_edit, name='college_admin_edit'),
    path('college-admins/<int:pk>/toggle-status/', admin_mgmt_views.college_admin_toggle_status, name='college_admin_toggle_status'),
    path('college-admins/<int:pk>/reset-password/', admin_mgmt_views.college_admin_reset_password, name='college_admin_reset_password'),
    path('audit-logs/', admin_mgmt_views.audit_log_list, name='audit_log_list'),

    # College Admin SaaS Portal
    path('college/dashboard/', college_views.college_dashboard, name='college_dashboard'),
    path('college/offer-letter/<int:pk>/detail/', college_views.college_offer_letter_detail_api, name='college_offer_letter_detail_api'),
    path('college/offer-letter/<int:pk>/download-pdf/', college_views.college_download_pdf, name='college_download_pdf'),
    path('college/offer-letters/download-selected-zip/', college_views.college_download_selected_zip, name='college_download_selected_zip'),
    path('college/offer-letters/download-filtered-zip/', college_views.college_download_filtered_zip, name='college_download_filtered_zip'),
    path('college/offer-letters/export-excel/', college_views.college_export_excel, name='college_export_excel'),
    path('college/offer-letters/export-csv/', college_views.college_export_csv, name='college_export_csv'),
    path('college/change-password/', college_views.college_change_password, name='college_change_password'),
]

