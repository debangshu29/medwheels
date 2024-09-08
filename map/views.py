from decimal import Decimal
from django.http import HttpResponseBadRequest, HttpResponseNotFound
from django.db.models import F, FloatField, DecimalField
from django.db.models import F, ExpressionWrapper, FloatField
from django.urls import reverse
from django.shortcuts import render, redirect
from django.http import JsonResponse
from .models import DriverLocation, Ride, Feedback
import json
import requests
from django.db.models import Min, ExpressionWrapper
from django.contrib.auth.decorators import login_required
import googlemaps
from verify.models import CustomUser
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from verify.models import Driver
from django.contrib import messages
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.conf import settings
import uuid
from django.contrib.auth import get_user_model
from django.views.decorators.csrf import csrf_exempt
import logging
from urllib.parse import urlencode
from .models import DriverRideLocationHistory
from django.views.decorators.http import require_GET
from django.db.models import Avg
from django.utils import timezone
from django.db.models import Sum
from datetime import timedelta
from .models import Hospital
from django.core.serializers import serialize
from geopy.distance import geodesic
User = get_user_model()


def main_page(request):
    # Logic for the main page
    return render(request, 'main_page.html')

def drive_page(request):

    return render(request, 'drive.html')

def business(request):

    return render(request, 'business.html')

def about(request):

    return render(request, 'about.html')

logger = logging.getLogger(__name__)
def ride_map(request, ride_id):
    try:
        ride = get_object_or_404(Ride, id=ride_id)
    except Ride.DoesNotExist:
        return render(request, 'ride_not_confirmed.html')

    if ride.is_confirmed:
        pickup_location = (ride.pickup_latitude, ride.pickup_longitude)
        driver_name = phone_number = license_number = number_plate = ambulance_type = driver_location = None

        if ride.driver:
            try:
                driver_location = DriverLocation.objects.get(driver=ride.driver)
            except DriverLocation.DoesNotExist:
                driver_location = None

            driver_name = f"{ride.driver.user.first_name} {ride.driver.user.last_name}".title()
            phone_number = ride.driver.user.username
            license_number = ride.driver.license_number
            number_plate = ride.driver.number_plate
            ambulance_type = ride.driver.ambulance_type
            car_model = ride.driver.car_name
            average_rating_tuple = ride.driver.average_rating,
            average_rating = average_rating_tuple[0]





        if driver_location is None or driver_location.latitude is None or driver_location.longitude is None:
            return HttpResponseBadRequest("Driver location or coordinates are missing")

        if pickup_location[0] is None or pickup_location[1] is None:
            return HttpResponseBadRequest("Pickup location coordinates are missing")

        driver_latitude = float(driver_location.latitude)
        driver_longitude = float(driver_location.longitude)
        pickup_latitude = float(pickup_location[0])
        pickup_longitude = float(pickup_location[1])

        # Calculate the estimated time and distance for the ride from pickup to drop-off
        ride_est_time, ride_est_distance = calculate_route(
            (pickup_latitude, pickup_longitude),
            (ride.drop_latitude, ride.drop_longitude)
        )
        # Mapping internal ambulance type values to display names
        ambulance_type_display_map = {
            'med_bls': 'Med BLS',
            'med_als': 'Med ALS',
            'med_icu': 'Med ICU',
        }
        # Get the display name or use the original if not found in the map
        ambulance_type_display = ambulance_type_display_map.get(ambulance_type, ambulance_type)

        # Calculate fare using the distance and ambulance type
        fare = calculate_fare(float(ride_est_distance.split()[0]), ambulance_type)

        # Calculate the driver's estimated time and distance to the pickup location
        driver_est_time, driver_est_distance = calculate_route(
            (driver_latitude, driver_longitude),
            (pickup_latitude, pickup_longitude)
        )

        google_maps_url = f"https://www.google.com/maps/dir/?api=1&" + urlencode({
            'origin': f"{driver_latitude},{driver_longitude}",
            'destination': f"{pickup_latitude},{pickup_longitude}",
            'travelmode': 'driving'
        })

        context = {
            'ride_id': ride_id,
            'driver_latitude': driver_latitude,
            'driver_longitude': driver_longitude,
            'pickup_latitude': pickup_latitude,
            'pickup_longitude': pickup_longitude,
            'driver_name': driver_name,
            'phone_number': phone_number,
            'license_number': license_number,
            'number_plate': number_plate,
            'ambulance_type': ambulance_type_display,
            'pickup': ride.pickup,
            'drop': ride.drop,
            'driver_est_time': driver_est_time,
            'driver_est_distance': driver_est_distance,
            'google_maps_url': google_maps_url,
            'estimated_time': ride_est_time,
            'estimated_distance': ride_est_distance,
            'fare': fare,
            'car_model': car_model,  # Add car name to context
            'average_rating': float(average_rating),
        }

        return render(request, 'ride_map.html', context)
    else:
        messages.error(request, 'Ride is not confirmed yet.')
        return render(request, 'ride_not_confirmed.html')








def ride_not_confirmed(request):
    return render(request, 'ride_not_confirmed.html')




@login_required
def dashboard(request):
    if hasattr(request.user, 'driver_profile'):
        driver = request.user.driver_profile
        ride = Ride.objects.filter(driver=driver, is_confirmed=True).last()  # Get the last confirmed ride

        # Fetch the last 5 rides for the ride history
        recent_rides = Ride.objects.filter(driver=driver, is_confirmed=True).order_by('-created_at')[:5]

        # Calculate earnings
        total_earnings = Ride.objects.filter(driver=driver, is_paid=True).aggregate(Sum('fare'))['fare__sum'] or 0

        # Calculate weekly earnings (last 7 days)
        one_week_ago = timezone.now() - timedelta(days=7)
        weekly_earnings = Ride.objects.filter(driver=driver, is_paid=True, created_at__gte=one_week_ago).aggregate(Sum('fare'))['fare__sum'] or 0

        # Calculate monthly earnings (last 30 days)
        one_month_ago = timezone.now() - timedelta(days=30)
        monthly_earnings = Ride.objects.filter(driver=driver, is_paid=True, created_at__gte=one_month_ago).aggregate(Sum('fare'))['fare__sum'] or 0

        # Prepare the context with required driver details and earnings
        context = {
            'driver_name': f"{driver.user.first_name} {driver.user.last_name}",
            'phone_number': driver.user.username,
            'license_number': driver.license_number,
            'ambulance_type': driver.get_ambulance_type_display(),
            'average_rating': driver.average_rating,
            'ride_id': ride.id if ride else None,
            'ride': ride,
            'number_plate': driver.number_plate,  # Add number plate to context
            'car_name': driver.car_name,  # Add car name to context
            'profile_image': driver.profile_image.url if driver.profile_image else None,  # Add profile image to context
            'recent_rides': recent_rides,
            'total_earnings': total_earnings,
            'weekly_earnings': weekly_earnings,
            'monthly_earnings': monthly_earnings,
            'range': range(1, 6),  # A range from 1 to 5 for star display
            'no_ride': ride is None,  # Flag to indicate if there's no ride
        }

        return render(request, 'dashboard.html', context)
    else:
        return redirect('/')  # Redirect to unauthorized page







@csrf_exempt
def update_location(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            latitude = data.get('latitude')
            longitude = data.get('longitude')
            location_name = data.get('location_name')

            if latitude is None or longitude is None:
                return JsonResponse({'error': 'Latitude or longitude missing'}, status=400)

            driver = request.user  # Assuming the authenticated user is a driver

            # Update or create DriverLocation
            driver_location, created = DriverLocation.objects.update_or_create(
                driver=driver.driver_profile,
                defaults={
                    'latitude': latitude,
                    'longitude': longitude,
                    'location_name': location_name
                }
            )

            return JsonResponse({'success': True, 'message': 'Location updated successfully'}, status=200)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    else:
        return JsonResponse({'error': 'Only POST requests are allowed'}, status=405)




def service_view(request):
    # Fetch all driver locations from the database
    locations = DriverLocation.objects.all()


    # Pass the locations to the template
    return render(request, 'service.html', {'locations': locations})


def calculate_fare(distance, ambulance_type):
    base_fare = 50.0  # Default base fare for Med BLS
    per_km_rate = 10.0  # Default per km rate for Med BLS

    if ambulance_type == 'med_als':
        base_fare += 30.0  # Additional base fare for Med ALS
        per_km_rate += 10.0  # Additional per km rate for Med ALS
    elif ambulance_type == 'med_icu':
        base_fare += 50.0  # Additional base fare for Med ICU
        per_km_rate += 20.0  # Additional per km rate for Med ICU

    return base_fare + (per_km_rate * distance)

def address_to_coordinates(address):
    gmaps = googlemaps.Client(key=settings.GOOGLE_MAPS_API_KEY)
    geocode_result = gmaps.geocode(address)
    if geocode_result and 'geometry' in geocode_result[0] and 'location' in geocode_result[0]['geometry']:
        location = geocode_result[0]['geometry']['location']
        return location['lat'], location['lng']
    else:
        return None, None


def get_distance_matrix(origins, destinations):
    gmaps = googlemaps.Client(key=settings.GOOGLE_MAPS_API_KEY)
    matrix = gmaps.distance_matrix(origins, destinations, mode="driving")
    return matrix


def dijkstra_algorithm(graph, start_node):
    unvisited_nodes = list(graph.keys())
    shortest_path = {}
    previous_nodes = {}
    max_value = float('inf')

    for node in unvisited_nodes:
        shortest_path[node] = max_value
    shortest_path[start_node] = 0

    while unvisited_nodes:
        current_min_node = None
        for node in unvisited_nodes:
            if current_min_node is None:
                current_min_node = node
            elif shortest_path[node] < shortest_path[current_min_node]:
                current_min_node = node

        neighbors = graph[current_min_node].items()
        for neighbor, weight in neighbors:
            tentative_value = shortest_path[current_min_node] + weight
            if tentative_value < shortest_path[neighbor]:
                shortest_path[neighbor] = tentative_value
                previous_nodes[neighbor] = current_min_node

        unvisited_nodes.remove(current_min_node)

    return previous_nodes, shortest_path

def ride_view(request):
    if request.method == 'POST':
        pickup_address = request.POST.get('pickup')
        drop_address = request.POST.get('drop')

        # Convert addresses to coordinates
        pickup_lat, pickup_lng = address_to_coordinates(pickup_address)
        drop_lat, drop_lng = address_to_coordinates(drop_address)

        if pickup_lat is not None and pickup_lng is not None and drop_lat is not None and drop_lng is not None:
            driver_locations = DriverLocation.objects.all()
            if not driver_locations:
                return HttpResponseBadRequest("No drivers available.")

            origins = [(float(pickup_lat), float(pickup_lng))]
            destinations = [(float(driver.latitude), float(driver.longitude)) for driver in driver_locations]

            matrix = get_distance_matrix(origins, destinations)

            graph = {}
            graph[(float(pickup_lat), float(pickup_lng))] = {}
            for i, element in enumerate(matrix['rows'][0]['elements']):
                distance = element['distance']['value']
                driver_location = (float(driver_locations[i].latitude), float(driver_locations[i].longitude))
                graph[(float(pickup_lat), float(pickup_lng))][driver_location] = distance
                graph[driver_location] = {}  # Initialize the driver's location in the graph

            previous_nodes, shortest_path = dijkstra_algorithm(graph, (float(pickup_lat), float(pickup_lng)))

            nearest_driver = None
            min_distance = float('inf')
            for driver in driver_locations:
                driver_node = (float(driver.latitude), float(driver.longitude))
                if driver_node in shortest_path and shortest_path[driver_node] < min_distance:
                    min_distance = shortest_path[driver_node]
                    nearest_driver = driver

            # Calculate the estimated time and distance for the driver to reach the pickup location
            driver_est_time, driver_est_distance = calculate_route(
                (nearest_driver.latitude, nearest_driver.longitude),
                (pickup_lat, pickup_lng)
            )

            # Calculate the estimated time and distance for the ride from pickup to drop-off
            ride_est_time, ride_est_distance = calculate_route(
                (pickup_lat, pickup_lng),
                (drop_lat, drop_lng)
            )

            ride_distance_km = float(ride_est_distance.split()[0])
            fare_medbls = calculate_fare(ride_distance_km, 'med_bls')
            fare_medals = calculate_fare(ride_distance_km, 'med_als')
            fare_medicu = calculate_fare(ride_distance_km, 'med_icu')

            context = {
                'pickup': pickup_address,
                'drop': drop_address,
                'driver_est_time': driver_est_time,
                'driver_est_distance': driver_est_distance,
                'ride_est_time': ride_est_time,
                'ride_est_distance': ride_est_distance,
                'pickup_lat': pickup_lat,
                'pickup_lng': pickup_lng,
                'drop_lat': drop_lat,
                'drop_lng': drop_lng,
                'fare_medbls': fare_medbls,
                'fare_medals': fare_medals,
                'fare_medicu': fare_medicu,
                'nearest_drivers': driver_locations  # Pass all nearby drivers to the template
            }

            return render(request, 'service1.html', context)
        else:
            return HttpResponseBadRequest("Invalid pickup or drop address.")

    return render(request, 'service1.html')



def calculate_route(start_location, end_location):
    # Unpack latitude and longitude from the start and end location tuples
    start_lat, start_lng = start_location
    end_lat, end_lng = end_location

    # Format coordinates without parentheses
    start_str = f"{start_lat},{start_lng}"
    end_str = f"{end_lat},{end_lng}"

    # Replace 'YOUR_API_KEY' with your actual Google Maps API key
    api_key = settings.GOOGLE_MAPS_API_KEY

    # Construct the API request URL
    url = f'https://maps.googleapis.com/maps/api/distancematrix/json?origins={start_str}&destinations={end_str}&key={api_key}'

    print("API Request URL:", url)  # Print API request URL for debugging

    try:
        # Send a GET request to the API
        response = requests.get(url)
        data = response.json()

        print("API Response:", data)  # Print the API response for debugging

        # Check if response status is OK
        if data['status'] == 'OK':
            # Extract estimated time and distance from the API response
            rows = data.get('rows', [])
            if rows:
                elements = rows[0].get('elements', [])
                if elements:
                    element = elements[0]
                    if element['status'] == 'OK':
                        estimated_time = element.get('duration', {}).get('text')
                        estimated_distance = element.get('distance', {}).get('text')
                        print(f"Estimated Time: {estimated_time}, Estimated Distance: {estimated_distance}")
                    else:
                        print("Error in element status:", element['status'])
                        estimated_time = "Not Available"
                        estimated_distance = "Not Available"
                else:
                    print("No elements found")
                    estimated_time = "Not Available"
                    estimated_distance = "Not Available"
            else:
                print("No rows found")
                estimated_time = "Not Available"
                estimated_distance = "Not Available"
        else:
            print("Response status not OK:", data['status'])
            estimated_time = "Not Available"
            estimated_distance = "Not Available"

    except Exception as e:
        # Handle API request errors
        print(f'Error: {e}')
        estimated_time = "Not Available"
        estimated_distance = "Not Available"

    return estimated_time, estimated_distance





@transaction.atomic
def save_booking_view(request):
    if request.method == 'POST':
        required_fields = [
            'pickup', 'drop', 'estimated_time', 'estimated_distance', 'pickup_lat',
            'pickup_lng', 'drop_lat', 'drop_lng', 'ambulance_type', 'fare'
        ]
        if not all(field in request.POST for field in required_fields):
            return HttpResponseBadRequest("Required fields are missing in the request.")

        pickup = request.POST['pickup']
        drop = request.POST['drop']
        pickup_lat = Decimal(request.POST['pickup_lat'])
        pickup_lng = Decimal(request.POST['pickup_lng'])
        drop_lat = Decimal(request.POST['drop_lat'])
        drop_lng = Decimal(request.POST['drop_lng'])
        ambulance_type = request.POST['ambulance_type']
        fare = Decimal(request.POST['fare'])

        # Correct query: Get driver locations with the specified ambulance type
        driver_locations = DriverLocation.objects.filter(driver__ambulance_type=ambulance_type)

        if not driver_locations:
            messages.error(request, 'No available drivers with the specified ambulance type. Please try again later.')
            return render(request, 'service1.html')

        origins = [(pickup_lat, pickup_lng)]
        destinations = [(driver.latitude, driver.longitude) for driver in driver_locations]

        matrix = get_distance_matrix(origins, destinations)

        graph = {(pickup_lat, pickup_lng): {}}
        for i, driver_location in enumerate(driver_locations):
            driver_node = (driver_location.latitude, driver_location.longitude)
            distance = matrix['rows'][0]['elements'][i]['distance']['value']  # distance in meters
            distance_km = distance / 1000.0  # convert to kilometers
            graph[(pickup_lat, pickup_lng)][driver_node] = distance_km
            graph[driver_node] = {}

        previous_nodes, shortest_paths = dijkstra_algorithm(graph, (pickup_lat, pickup_lng))
        nearest_driver_node = min(shortest_paths, key=lambda k: shortest_paths[k] if k != (pickup_lat, pickup_lng) else float('inf'))
        nearest_driver = driver_locations.get(latitude=nearest_driver_node[0], longitude=nearest_driver_node[1])

        if nearest_driver:
            driver = nearest_driver.driver

            # Calculate estimated time and distance for the ride from pickup to drop-off
            ride_est_time, ride_est_distance = calculate_route((pickup_lat, pickup_lng), (drop_lat, drop_lng))

            ride = Ride.objects.create(
                driver=driver,
                user=request.user,
                pickup=pickup,
                drop=drop,
                estimated_time=ride_est_time,  # Save estimated time
                estimated_distance=ride_est_distance,  # Save estimated distance
                pickup_latitude=pickup_lat,
                pickup_longitude=pickup_lng,
                drop_latitude=drop_lat,  # Ensure drop coordinates are saved
                drop_longitude=drop_lng,  # Ensure drop coordinates are saved
                ambulance_type=ambulance_type,
                fare=fare,
                is_confirmed=False
            )

            ride.token = generate_unique_token()
            ride.save()

            send_ride_request_email(request, ride)

            messages.success(request, 'Booking requested successfully. Waiting for driver confirmation.')

            return render(request, 'booking_success.html', {
                'ride_id': ride.id,
                'pickup': pickup,
                'drop': drop,
                'estimated_time': ride_est_time,
                'estimated_distance': ride_est_distance,
                'pickup_latitude': pickup_lat,
                'pickup_longitude': pickup_lng,
                'drop_latitude': drop_lat,
                'drop_longitude': drop_lng,
                'fare': fare,
                'ambulance_type': ambulance_type,
                'driver_latitude': nearest_driver_node[0],
                'driver_longitude': nearest_driver_node[1],
                'driver_name': driver.user.first_name + ' ' + driver.user.last_name,  # Correct access to CustomUser
                'phone_number': driver.user.username,  # Correct access to CustomUser
                'license_number': driver.license_number,
                'number_plate': driver.number_plate
            })
        else:
            messages.error(request, 'No available drivers. Please try again later.')
            return redirect('service1')

    return HttpResponseBadRequest("Invalid request method.")



def booking_success(request):
    # Check if the booking request is sent and confirmed
    if request.session.get('ride_confirmed'):
        # If the ride is confirmed, redirect to ride_map
        ride_id = request.session.get('ride_id')
        if ride_id:
            return redirect('ride_map', ride_id=ride_id)
    else:
        # If the ride is not confirmed, render the booking success page
        return render(request, 'booking_success.html')





def generate_unique_token():
    # Generate a unique token for ride confirmation
    return uuid.uuid4().hex[:16]

def send_ride_request_email(request, ride):
    # Construct the accept and reject URLs with the token
    accept_url = request.build_absolute_uri(f'/accept-ride-by-email/?token={ride.token}')
    reject_url = request.build_absolute_uri(f'/reject-ride-by-email/?token={ride.token}')

    # Render the email template with context
    context = {
        'pickup': ride.pickup,
        'drop': ride.drop,
        'estimated_time': ride.estimated_time,
        'estimated_distance': ride.estimated_distance,
        'fare': ride.fare,
        'accept_url': accept_url,
        'reject_url': reject_url,
    }
    email_html_message = render_to_string('ride_request_email.html', context)
    plain_message = strip_tags(email_html_message)

    # Send the email
    subject = 'New Ride Request'
    sender = settings.EMAIL_HOST_USER  # Your Gmail email address
    recipient = ride.driver.user.email  # Driver's email address

    send_mail(
        subject,
        plain_message,
        sender,
        [recipient],
        html_message=email_html_message,
    )


def accept_ride_by_email(request):
    if request.method == 'GET':
        token = request.GET.get('token')

        # Try to retrieve the ride object associated with the token
        ride = Ride.objects.filter(token=token).first()

        if ride:
            # If the ride exists, update its status to 'confirmed'
            ride.is_confirmed = True
            ride.save()
            send_code_to_user(ride.id, ride.code)
            # Set session variable to indicate ride confirmation
            request.session['ride_confirmed'] = True

            # Send notification to the user (passenger) confirming the ride
            # Implement your notification logic here
            return redirect('ride_map', ride_id=ride.id)
        else:
            messages.error(request, 'Invalid token or ride already confirmed.')
            return redirect('dashboard')
    else:
        return HttpResponseBadRequest("Invalid request method.")

def driver_reject(request):
    return render(request,'driver_reject.html')

def reject_ride_by_email(request):
    if request.method == 'GET':
        token = request.GET.get('token')

        # Try to retrieve the ride object associated with the token
        ride = Ride.objects.filter(token=token).first()

        if ride:
            # If the ride exists, delete it from the database or update its status to indicate rejection
            ride.delete()  # You can adjust this to update status instead of deleting

            messages.info(request, 'Ride rejected via email. Booking not confirmed.')

            return render(request, 'driver_reject.html')  # Redirect back to the driver reject page after rejecting the ride via email
        else:
            messages.error(request, 'Invalid token or ride not found.')
            return redirect('dashboard')
    else:
        return HttpResponseBadRequest("Invalid request method.")


def verify_ride(request, ride_id):
    ride = get_object_or_404(Ride, id=ride_id)

    if request.method == 'POST':
        try:
            # Parse the JSON data from the request body
            data = json.loads(request.body)
            entered_code = data.get('code')
        except ValueError:
            return HttpResponseBadRequest("Invalid JSON data")

        # Log the entered and actual code for debugging
        logger.info(f"Entered code: {entered_code}, Actual code: {ride.code}")

        if entered_code == ride.code:
            ride.is_verified = True
            ride.status = 'verified'
            ride.save()

            return JsonResponse({'success': True})
        else:
            logger.error("Verification code is incorrect.")
            return JsonResponse({'success': False, 'error': 'Verification code is incorrect.'})

    return render(request, 'ride_map.html', {'ride': ride})




@login_required
def check_ride_status(request, ride_id):
    """
    Checks if the ride is verified.
    """
    ride = get_object_or_404(Ride, id=ride_id)
    return JsonResponse({'is_verified': ride.is_verified})

def generate_and_send_code(request, ride_id):
    try:
        # Retrieve the ride object
        ride = Ride.objects.get(id=ride_id)
    except Ride.DoesNotExist:
        # Handle the case where the ride object does not exist
        return HttpResponseBadRequest("Invalid ride ID.")

    # Generate a unique 4-digit code
    code = generate_unique_4_digit_code()

    # Associate the code with the ride
    ride.pickup_code = code
    ride.save()

    # Send the code to the user (send via email, SMS, etc.)
    send_code_to_user(ride.user.email, code)

    # Generate the URL for the verify_code view
    url = reverse('verify_code', kwargs={'ride_id': ride_id})  # Pass the ride_id parameter

    # Render a page indicating that the code is sent
    return render(request, 'code_sent.html', {'verification_url': request.build_absolute_uri(url)})




@login_required
def drop_map(request, ride_id):
    # Retrieve the ride and necessary details for displaying the map
    ride = get_object_or_404(Ride, id=ride_id)
    pickup_location = (ride.pickup_latitude, ride.pickup_longitude)
    drop_location = (ride.drop_latitude, ride.drop_longitude)
    driver_name = f"{ride.driver.user.first_name} {ride.driver.user.last_name}".title()
    phone_number = ride.driver.user.username
    license_number = ride.driver.license_number
    number_plate = ride.driver.number_plate
    ambulance_type = ride.driver.ambulance_type
    car_model = ride.driver.car_name
    average_rating_tuple = ride.driver.average_rating,
    average_rating = average_rating_tuple[0]
    # Construct the Google Maps URL for navigation from pickup to drop-off
    google_maps_url = f"https://www.google.com/maps/dir/?api=1&origin={pickup_location[0]},{pickup_location[1]}&destination={drop_location[0]},{drop_location[1]}&travelmode=driving"

    # Mapping internal ambulance type values to display names
    ambulance_type_display_map = {
        'med_bls': 'Med BLS',
        'med_als': 'Med ALS',
        'med_icu': 'Med ICU',
    }
    # Get the display name or use the original if not found in the map
    ambulance_type_display = ambulance_type_display_map.get(ambulance_type, ambulance_type)
    # Pass the necessary data to the template for displaying the map
    context = {
        'pickup_location': pickup_location,
        'drop_location': drop_location,
        'google_maps_url': google_maps_url,
        'ride': ride,  # Include ride object to check the user type in the template
        'ride_id': ride_id,
        'car_model': car_model,  # Add car name to context
        'average_rating': float(average_rating),
        'driver_name': driver_name,
        'phone_number': phone_number,
        'license_number': license_number,
        'number_plate': number_plate,
        'ambulance_type': ambulance_type_display,  # Use display name for ambulance type
    }

    return render(request, 'drop_map.html', context)


def generate_unique_4_digit_code():
    """
    Generate a unique 4-digit code.
    """
    return uuid.uuid4().hex[:4].upper()


def send_code_to_user(ride_id, code):
    """
    Send the generated code to the user via email.
    """
    try:
        # Retrieve the ride object
        ride = Ride.objects.get(id=ride_id)
    except Ride.DoesNotExist:
        # Handle the case where the ride object does not exist
        print("Ride does not exist.")
        return

    # Check if ride has a user associated with it
    if not ride.user:
        print("Ride does not have a user associated with it.")
        return

    # Check if the user has a valid email address
    user_email = ride.user.email
    if not user_email:
        print("User does not have a valid email address.")
        return

    subject = 'Your Pickup Code'
    message = f'Your pickup code is: {code}'
    sender = settings.EMAIL_HOST_USER

    # Print debug statements
    print(f"Sending email to: {user_email}")
    print(f"Email content: {message}")

    # Send the email
    send_mail(subject, message, sender, [user_email])

    print("Email sent successfully.")



def get_latest_driver_location(request, driver_id):
    try:
        # Fetch the latest location of the driver
        driver_location = DriverLocation.objects.get(driver__id=driver_id)
        return JsonResponse({
            'latitude': str(driver_location.latitude),
            'longitude': str(driver_location.longitude)
        }, status=200)
    except DriverLocation.DoesNotExist:
        return JsonResponse({'error': 'Driver location not found'}, status=404)

logger = logging.getLogger(__name__)

@login_required
@require_GET
def get_driver_location(request, ride_id):
    try:
        # Log the incoming request
        logger.info(f"Fetching driver location for ride_id: {ride_id}")

        # Fetch the latest driver location for the given ride ID
        driver_location = DriverLocation.objects.filter(ride_id=ride_id).latest('timestamp')

        # If the location is found, return it as a JSON response
        if driver_location:
            data = {
                'latitude': driver_location.latitude,
                'longitude': driver_location.longitude,

            }
            logger.info(f"Driver location found: {data}")
            return JsonResponse(data)
        else:
            # Log if no location is found and return a 404 response
            logger.warning(f"No driver location found for ride_id {ride_id}")
            return JsonResponse({'error': 'Driver location not found.'}, status=404)

    except DriverLocation.DoesNotExist:
        # Log the specific error when the driver location does not exist
        logger.error(f"DriverLocation.DoesNotExist: No driver location found for ride_id {ride_id}")
        return JsonResponse({'error': 'Driver location not found.'}, status=404)

    except Exception as e:
        # Log any other unexpected errors
        logger.error(f"Exception occurred while fetching driver location for ride_id {ride_id}: {str(e)}")
        return JsonResponse({'error': f'Internal server error: {str(e)}'}, status=500)


logger = logging.getLogger(__name__)

@login_required
def get_driver_location_by_ride(request, ride_id):
    try:
        logger.info(f"Fetching driver location for ride_id: {ride_id}")

        # Fetch the ride object
        ride = get_object_or_404(Ride, id=ride_id)

        # Access the DriverLocation directly using the related name 'driver_location'
        driver_location = ride.driver.driver_location

        # If the location is found, return it as a JSON response
        data = {
            'latitude': driver_location.latitude,
            'longitude': driver_location.longitude,
        }
        logger.info(f"Driver location found: {data}")
        return JsonResponse(data)

    except DriverLocation.DoesNotExist:
        logger.error(f"No driver location found for ride_id {ride_id}")
        return JsonResponse({'error': 'Driver location not found.'}, status=404)

    except Exception as e:
        logger.error(f"Error fetching driver location for ride_id {ride_id}: {str(e)}")
        return JsonResponse({'error': f'Internal server error: {str(e)}'}, status=500)


@login_required
@csrf_exempt
def complete_ride(request, ride_id):
    """
    Marks the ride as completed and redirects driver and user to payment pages.
    """
    if request.method == 'POST':
        try:
            ride = get_object_or_404(Ride, id=ride_id)
            ride.is_completed = True
            ride.status = 'completed'
            ride.save()

            return JsonResponse({
                'success': True,
                'driver_redirect_url': redirect('driver_payment', ride_id=ride.id).url,
                'user_redirect_url': redirect('user_payment', ride_id=ride.id).url
            })
        except Ride.DoesNotExist:
            return JsonResponse({'error': 'Ride not found'}, status=404)
    return JsonResponse({'error': 'Invalid request method'}, status=400)


@login_required
@csrf_exempt
def confirm_payment(request, ride_id):
    if request.method == 'POST':
        try:
            ride = get_object_or_404(Ride, id=ride_id)
            ride.is_paid = True
            ride.payment_confirmed = True
            ride.is_completed = True
            ride.save()

            if request.user.is_driver:
                # Redirect driver to the main page
                return JsonResponse({'success': True, 'redirect_url': '/'})
        except Ride.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Ride not found'}, status=404)
    return JsonResponse({'success': False, 'error': 'Invalid request method'}, status=400)


@login_required
def get_ride_completion_status(request, ride_id):
    """
    Checks if the ride is completed and returns the appropriate URLs for redirection.
    """
    try:
        ride = get_object_or_404(Ride, id=ride_id)
        if ride.is_completed:
            return JsonResponse({
                'is_completed': True,
                'driver_redirect_url': redirect('driver_payment', ride_id=ride.id).url,
                'user_redirect_url': redirect('user_payment', ride_id=ride.id).url
            })
        else:
            return JsonResponse({'is_completed': False})
    except Ride.DoesNotExist:
        return JsonResponse({'error': 'Ride not found'}, status=404)






def payment_page(request, ride_id):
    if request.user.is_driver:
        return render(request, 'driver_payment.html', {'ride_id': ride_id})
    else:
        return render(request, 'user_payment.html', {'ride_id': ride_id})

@login_required
def user_payment(request, ride_id):
    # Your logic for user payment
    return render(request, 'user_payment.html', {'ride_id': ride_id})

@login_required
def driver_payment(request, ride_id):
    # Your logic for driver payment
    return render(request, 'driver_payment.html', {'ride_id': ride_id})

@login_required
def feedback(request, ride_id):
    ride = get_object_or_404(Ride, id=ride_id)

    if request.method == 'POST':
        rating = request.POST.get('rating')
        comments = request.POST.get('comments')
        selected_options = request.POST.getlist('options')  # Get the list of selected options

        # Validate the rating
        try:
            rating = float(rating)
        except (TypeError, ValueError):
            rating = None

        if rating is None or rating < 1 or rating > 5:
            messages.error(request, "Invalid rating value.")
            return render(request, 'feedback.html', {'ride': ride})

        try:
            # Create and save the feedback
            Feedback.objects.create(
                ride=ride,
                rating=rating,
                comments=comments,
                selected_options=','.join(selected_options)  # Join options into a comma-separated string
            )
            messages.success(request, "Feedback successfully submitted!")
        except Exception as e:
            messages.error(request, "An error occurred while saving feedback.")
            print(f"Error: {e}")  # Log the error for debugging

        # Redirect to a 'thank you' page or another relevant page
        return redirect('/')  # Replace with your actual redirect

    return render(request, 'feedback.html', {'ride': ride})


@login_required
def check_payment_status(request, ride_id):
    ride = get_object_or_404(Ride, id=ride_id)

    if ride.payment_confirmed:
        # Redirect user to the feedback page
        return JsonResponse({'success': True, 'redirect_url': f'/ride/{ride_id}/feedback/'})
    else:
        # Payment is not confirmed yet
        return JsonResponse({'success': False, 'message': 'Payment not confirmed yet.'})








logger = logging.getLogger(__name__)

@csrf_exempt
def update_driver_location(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            latitude = data.get('lat')
            longitude = data.get('lng')

            if latitude is None or longitude is None:
                return JsonResponse({'success': False, 'error': 'Latitude and longitude are required'}, status=400)

            # Retrieve the Driver instance associated with the authenticated user
            try:
                driver = Driver.objects.get(user=request.user)
            except Driver.DoesNotExist:
                logger.error(f"Driver not found for user: {request.user.id}")
                return JsonResponse({'success': False, 'error': 'Driver not found'}, status=404)

            # Update or create the driver's current location
            DriverLocation.objects.update_or_create(
                driver=driver,
                defaults={'latitude': latitude, 'longitude': longitude}
            )

            logger.info(f"Location updated successfully for driver: {driver.id}")
            return JsonResponse({'success': True, 'message': 'Location updated successfully'}, status=200)
        except Exception as e:
            logger.error(f"Error in update_driver_location: {str(e)}")
            return JsonResponse({'success': False, 'error': str(e)}, status=500)
    else:
        logger.warning(f"Invalid request method: {request.method}")
        return JsonResponse({'success': False, 'error': 'Invalid request method'}, status=405)

@login_required
def edit_driver_profile(request):
    driver = request.user.driver_profile  # Get the driver profile linked to the logged-in user
    if request.method == 'POST':
        # Update the driver's details
        driver.license_number = request.POST.get('license_number')
        driver.number_plate = request.POST.get('number_plate')
        driver.ambulance_type = request.POST.get('ambulance_type')
        driver.car_name = request.POST.get('car_name')

        # Handle profile image update if provided
        if request.FILES.get('profile_image'):
            driver.profile_image = request.FILES.get('profile_image')

        # Update user details
        request.user.first_name = request.POST.get('first_name')
        request.user.last_name = request.POST.get('last_name')
        request.user.username = request.POST.get('phone')

        # Save the changes
        request.user.save()
        driver.save()

        return redirect('dashboard')  # Redirect to the driver's profile page after saving
    else:
        # Render the edit form with current profile data
        context = {
            'user': request.user,
            'driver': driver,
        }
        return render(request, 'edit_profile.html', context)

def hospital_list(request):
    return render(request, 'hospital_list.html')

def get_nearby_hospitals(request):
    user_latitude = request.GET.get('latitude')
    user_longitude = request.GET.get('longitude')

    if user_latitude and user_longitude:
        user_location = (float(user_latitude), float(user_longitude))

        # Fetch all hospitals
        hospitals = Hospital.objects.all()
        hospital_distances = []

        # Calculate distance from user location to each hospital
        for hospital in hospitals:
            hospital_location = (hospital.latitude, hospital.longitude)
            distance = geodesic(user_location, hospital_location).kilometers
            hospital_distances.append((hospital, distance))

        # Sort hospitals by distance
        hospital_distances.sort(key=lambda x: x[1])

        # Serialize sorted hospitals
        serialized_hospitals = [
            {
                "id": hospital.id,
                "name": hospital.name,
                "address": hospital.address,
                "phone_number": hospital.phone_number,
                "latitude": str(hospital.latitude),
                "longitude": str(hospital.longitude),
                "website": hospital.website,
                "rating": float(hospital.rating) if hospital.rating else None,
                "distance": round(distance, 2)  # Include distance for display
            }
            for hospital, distance in hospital_distances
        ]
        return JsonResponse(serialized_hospitals, safe=False)
    else:
        return JsonResponse({'error': 'Unable to get user location'}, status=400)

def new_service(request):
    if request.method == 'POST':
        hospital_id = request.POST.get('hospital_id')
        drop = request.POST.get('drop')
    else:  # fallback for GET requests if needed
        hospital_id = request.GET.get('hospital_id')
        drop = request.GET.get('drop')

    hospital = get_object_or_404(Hospital, id=hospital_id)

    context = {
        'drop': drop,
        'hospital': hospital
    }

    return render(request, 'new_service.html', context)