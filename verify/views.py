from django.shortcuts import render, redirect
from django.contrib import messages
from .models import CustomUser, Driver
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required


# Create your views here.

def main_view(request):
    return render(request, 'main.html')



def signup_view(request):
    if request.user.is_authenticated:
        return redirect('/')  # Redirect authenticated users
    if request.method == 'POST':
        # Retrieve form data
        first_name = request.POST.get('first_name')
        last_name = request.POST.get('last_name')
        phone = request.POST.get('phone')
        email = request.POST.get('email')
        password = request.POST.get('password')
        is_driver = request.POST.get('is_driver')

        # Perform data validation
        phone_check = CustomUser.objects.filter(username=phone).exists()
        email_check = CustomUser.objects.filter(email=email).exists()
        if phone_check:
            messages.error(request, 'Your Phone Number Already Exists')
            return redirect('signup')
        if email_check:
            messages.error(request, 'Your Email Already Exists')
            return redirect('signup')
        if len(phone) != 10:
            messages.error(request, 'Phone Number should be 10 digits')
            return redirect('signup')

        # Create new user
        user = CustomUser.objects.create_user(username=phone, email=email, password=password)
        user.first_name = first_name
        user.last_name = last_name
        user.save()

        # Handle driver-specific data if applicable
        if is_driver == 'on':
            license_number = request.POST.get('license_number')
            number_plate = request.POST.get('number_plate')
            ambulance_type = request.POST.get('ambulance_type')
            driver = Driver.objects.create(user=user, license_number=license_number, number_plate=number_plate, ambulance_type=ambulance_type)
            driver.save()
            user.is_driver = True
            messages.success(request, 'Signup successful! You are now registered as a driver.')
        else:
            messages.success(request, 'Signup successful! You are now registered as a regular user.')
        user.save()
        return redirect('login')  # Redirect to login page after successful signup
    else:
        return render(request, 'signup.html')



def login_view(request):
    if request.user.is_authenticated:
        return redirect('/')
    if request.method == 'POST':
        phone = request.POST['phone']
        password = request.POST['password']
        user = authenticate(request, username=phone, password=password)
        if user is not None:
            login(request, user)
            if user.is_driver:
                # Redirect to the driver dashboard
                return redirect('dashboard')  # Replace 'driver_dashboard' with the actual URL name of the driver dashboard
            else:
                # Redirect to the home page
                return redirect('/')  # Replace '/' with the actual URL of the home page
        else:
            messages.error(request, 'Invalid username or password.')
    return render(request, 'login.html')

def logout_view(request):
    logout(request)
    messages.info(request, 'You have been logged out.')
    return redirect('login')  # Redirect to login page after logout

@login_required
def driver_dashboard_view(request):
    # Logic to fetch driver-specific data
    driver = request.user.driver_profile  # Assuming CustomUser has a one-to-one relation with Driver

    context = {
        'driver': driver,  # Pass driver data to the template
        # Add any additional context data needed for the template
    }
    return render(request, 'dashboard.html', context)

# @driver_required
# def restricted_view(request):
#     # This view is restricted to authenticated drivers only
#     return render(request, 'driver_dashboard.html')