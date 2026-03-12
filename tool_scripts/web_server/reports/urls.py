"""
URL configuration for reports app
"""
from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('reports/', views.report_list, name='report_list'),
    path('reports/<str:slug>/', views.report_detail, name='report_detail'),
    path('reports/<str:slug>/pdf/', views.report_pdf, name='report_pdf'),
    path('charts/<str:ticker>/', views.chart_page, name='chart_page'),
    path('api/price-history/', views.api_price_history, name='api_price_history'),
]
