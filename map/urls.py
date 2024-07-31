# In urls.py

from django.urls import path
from map import views

urlpatterns = [
    # Other URL patterns...
    path('update_location/', views.update_location, name='update_location'),
    path('service/', views.service_view, name='service'),
    path('ride', views.ride_view, name='ride_view'),
    path('dashboard', views.dashboard, name='dashboard'),
    path('save_booking', views.save_booking_view, name='save_booking'),
    # path('confirm_ride', views.confirm_ride, name="confirm_ride"),
    path('booking_success', views.booking_success, name='booking_success'),
    path('accept-ride-by-email/', views.accept_ride_by_email, name='accept_ride_by_email'),
    path('reject-ride-by-email/', views.reject_ride_by_email, name='reject_ride_by_email'),
    path('ride_map/<int:ride_id>/', views.ride_map, name='ride_map'),
    path('ride_not_confirmed', views.ride_not_confirmed, name='ride_not_confirmed'),
    path('verify-code/<int:ride_id>/', views.verify_code, name='verify_code'),
    path('generate-and-send-code/<int:ride_id>/', views.generate_and_send_code, name='generate_and_send_code'),
    path('display-map/<int:ride_id>/', views.display_map, name='display_map'),
    path('driver_reject/', views.driver_reject, name='driver_reject'),



]
