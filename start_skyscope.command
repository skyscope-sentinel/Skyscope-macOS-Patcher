#!/bin/bash
#
# start_skyscope.command
# Launcher Script for Skyscope Sentinel Intelligence Patcher
#
# This script provides a menu interface to choose between building,
# installing, or cleaning the Skyscope Sentinel Intelligence Patcher.
#
# Copyright (c) 2025 Skyscope Sentinel Intelligence
# Developer: Casey Jay Topojani
#

# Change to the script's directory
cd "$(dirname "$0")"

# Color codes for prettier output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
WHITE='\033[1;37m'
NC='\033[0m' # No Color

# Clear screen function
clear_screen() {
    clear
}

# Function to display the header
display_header() {
    clear_screen
    echo -e "${CYAN}=================================================${NC}"
    echo -e "${WHITE}   Skyscope Sentinel Intelligence Patcher v1.0.0  ${NC}"
    echo -e "${CYAN}=================================================${NC}"
    echo -e "${PURPLE}      Developer: Casey Jay Topojani              ${NC}"
    echo -e "${CYAN}=================================================${NC}"
    echo
}

# Function to display the menu
display_menu() {
    echo -e "${YELLOW}Please select an option:${NC}"
    echo
    echo -e "${GREEN}1)${NC} Build Skyscope Sentinel Intelligence Patcher"
    echo -e "${GREEN}2)${NC} Install Skyscope Sentinel Intelligence Patcher"
    echo -e "${GREEN}3)${NC} Clean build artifacts"
    echo -e "${GREEN}4)${NC} Show help information"
    echo -e "${GREEN}5)${NC} Exit"
    echo
    echo -n -e "${YELLOW}Enter your choice [1-5]:${NC} "
}

# Function to execute the selected option
execute_option() {
    local choice=$1
    
    case $choice in
        1)
            echo
            echo -e "${BLUE}Building Skyscope Sentinel Intelligence Patcher...${NC}"
            echo
            ./skyscope_sentinel_compiler.sh --build
            ;;
        2)
            echo
            echo -e "${BLUE}Installing Skyscope Sentinel Intelligence Patcher...${NC}"
            echo
            ./skyscope_sentinel_compiler.sh --install
            ;;
        3)
            echo
            echo -e "${BLUE}Cleaning build artifacts...${NC}"
            echo
            ./skyscope_sentinel_compiler.sh --clean
            ;;
        4)
            echo
            echo -e "${BLUE}Showing help information...${NC}"
            echo
            ./skyscope_sentinel_compiler.sh --help
            ;;
        5)
            echo
            echo -e "${GREEN}Exiting...${NC}"
            exit 0
            ;;
        *)
            echo
            echo -e "${RED}Invalid option. Please try again.${NC}"
            ;;
    esac
}

# Function to wait for user to press Enter
wait_for_enter() {
    echo
    echo -e "${YELLOW}Press Enter to continue...${NC}"
    read
}

# Check if skyscope_sentinel_compiler.sh exists and is executable
if [ ! -f "skyscope_sentinel_compiler.sh" ]; then
    display_header
    echo -e "${RED}Error: skyscope_sentinel_compiler.sh not found!${NC}"
    echo -e "${YELLOW}Please make sure you are running this script from the Skyscope-macOS-Patcher directory.${NC}"
    wait_for_enter
    exit 1
fi

if [ ! -x "skyscope_sentinel_compiler.sh" ]; then
    display_header
    echo -e "${RED}Error: skyscope_sentinel_compiler.sh is not executable!${NC}"
    echo -e "${YELLOW}Making skyscope_sentinel_compiler.sh executable...${NC}"
    chmod +x skyscope_sentinel_compiler.sh
    
    if [ $? -ne 0 ]; then
        echo -e "${RED}Failed to make skyscope_sentinel_compiler.sh executable.${NC}"
        echo -e "${YELLOW}Please run: chmod +x skyscope_sentinel_compiler.sh${NC}"
        wait_for_enter
        exit 1
    else
        echo -e "${GREEN}Successfully made skyscope_sentinel_compiler.sh executable.${NC}"
    fi
fi

# Main loop
while true; do
    display_header
    display_menu
    
    read choice
    
    execute_option $choice
    
    wait_for_enter
done
