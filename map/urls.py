from django.urls import path
from map import views
from django.conf.urls.static import static
from django.conf import settings

urlpatterns = [
    # Other URL patterns...
    path('', views.main_page, name='main_page'),
    path('about', views.about, name='about'),
    path('business', views.business, name='business'),
    path('drive_page', views.drive_page, name='drive_page'),
    path('update_location/', views.update_location, name='update_location'),
    path('service/', views.service_view, name='service'),
    path('ride', views.ride_view, name='ride_view'),
    path('dashboard', views.dashboard, name='dashboard'),
    path('save_booking', views.save_booking_view, name='save_booking'),
    path('booking_success', views.booking_success, name='booking_success'),
    path('accept-ride-by-email/', views.accept_ride_by_email, name='accept_ride_by_email'),
    path('reject-ride-by-email/', views.reject_ride_by_email, name='reject_ride_by_email'),
    path('ride_map/<int:ride_id>/', views.ride_map, name='ride_map'),
    path('ride_not_confirmed', views.ride_not_confirmed, name='ride_not_confirmed'),
    path('verify_ride/<int:ride_id>/', views.verify_ride, name='verify_ride'),
    path('generate-and-send-code/<int:ride_id>/', views.generate_and_send_code, name='generate_and_send_code'),
    path('drop_map/<int:ride_id>/', views.drop_map, name='drop_map'),  # Drop Map URL
    path('driver_reject/', views.driver_reject, name='driver_reject'),
    path('check_ride_status/<int:ride_id>/', views.check_ride_status, name='check_ride_status'),
    path('new_service/', views.new_service, name='new_service'),
    path('ride/<int:ride_id>/confirm-payment/', views.confirm_payment, name='confirm_payment'),
    path('user_payment/<int:ride_id>/', views.user_payment, name='user_payment'),
    path('driver_payment/<int:ride_id>/', views.driver_payment, name='driver_payment'),
    path('ride/<int:ride_id>/complete/', views.complete_ride, name='complete_ride'),
    path('ride/<int:ride_id>/feedback/', views.feedback, name='feedback'),  # Feedback page
    path('ride/<int:ride_id>/check-payment-status/', views.check_payment_status, name='check_payment_status'),
    path('ride/<int:ride_id>/completion_status/', views.get_ride_completion_status, name='get_ride_completion_status'),
    path('edit-profile/', views.edit_driver_profile, name='edit_profile'),
    path('get_latest_driver_location/<int:driver_id>/', views.get_latest_driver_location, name='get_latest_driver_location'),
    path('update_driver_location/', views.update_driver_location, name='update_driver_location'),
    path('ride/<int:ride_id>/driver-location/', views.get_driver_location, name='get_driver_location'),
    path('ride/<int:ride_id>/driver_location/', views.get_driver_location_by_ride, name='driver_location'),
    path('hospitals/', views.hospital_list, name='hospital_list'),
    path('get_nearby_hospitals/', views.get_nearby_hospitals, name='get_nearby_hospitals'),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)


